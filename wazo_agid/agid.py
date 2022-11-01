# -*- coding: utf-8 -*-
# Copyright 2008-2022 The Wazo Authors  (see the AUTHORS file)
# SPDX-License-Identifier: GPL-3.0-or-later

import signal
import logging
import SocketServer

from tenacity import after_log, before_log, retry, stop_after_attempt, wait_fixed
from threading import Lock

from xivo import agitb
from xivo import anysql
from xivo import moresynchro
from xivo.BackSQL import backpostgresql  # noqa
from wazo_agid import fastagi
from xivo_dao.helpers.db_utils import session_scope


logger = logging.getLogger(__name__)

_server = None
_handlers = {}


class DBConnectionPool(object):
    def __init__(self):
        self.conns = []
        self.size = 0
        self.db_uri = None
        self.lock = Lock()

    def reload(self, size, db_uri):
        with self.lock:
            for conn in self.conns:
                conn.close()

            self._wait_is_ready(db_uri)
            self.conns = [anysql.connect_by_uri(db_uri) for _ in xrange(size)]

            self.size = size
            self.db_uri = db_uri
        logger.debug("reloaded db conn pool")

    @retry(
        stop=stop_after_attempt(60 * 5),
        wait=wait_fixed(1),
        before=before_log(logger, logging.INFO),
        after=after_log(logger, logging.WARN),
    )
    def _wait_is_ready(self, db_uri):
        try:
            conn = anysql.connect_by_uri(db_uri)
        except Exception as e:
            logger.warning('fail to connect to the database: %s', e)
            raise
        conn.close()

    def acquire(self):
        with self.lock:
            try:
                conn = self.conns.pop()
                logger.debug("acquiring connection: got connection from pool")
            except IndexError:
                conn = anysql.connect_by_uri(self.db_uri)
                logger.debug("acquiring connection: pool empty, created new connection")

        return conn

    def release(self, conn):
        with self.lock:
            if len(self.conns) < self.size:
                self.conns.append(conn)
                logger.debug("releasing connection: pool not full, refilled with connection")
            else:
                conn.close()
                logger.debug("releasing connection: pool full, connection closed")


class FastAGIRequestHandler(SocketServer.StreamRequestHandler):

    def handle(self):
        try:
            logger.debug("handling request")

            fagi = fastagi.FastAGI(self.rfile, self.wfile, self.config)
            except_hook = agitb.Hook(agi=fagi)

            conn = self.server.db_conn_pool.acquire()
            try:
                cursor = conn.cursor()

                handler_name = fagi.env['agi_network_script']
                logger.debug("delegating request handling %r", handler_name)

                _handlers[handler_name].handle(fagi, cursor, fagi.args)

                conn.commit()

                fagi.verbose('AGI handler %r successfully executed' % handler_name)
                logger.debug("request successfully handled")
            finally:
                self.server.db_conn_pool.release(conn)

        # Attempt to relay errors to Asterisk, but if it fails, we
        # just give up.
        # XXX It may be here that dropping database connection
        # exceptions could be catched.
        except fastagi.FastAGIDialPlanBreak as message:
            logger.info("invalid request, dial plan broken")

            try:
                fagi.verbose(message)
                # TODO: see under
                fagi.appexec('Goto', 'agi_fail,s,1')
                fagi.fail()
            except Exception:
                pass
        except:
            logger.exception("unexpected exception")

            try:
                except_hook.handle()
                # TODO: (important!)
                #   - rename agi_fail, or find a better way
                #   - move at the beginning of a safe block
                fagi.appexec('Goto', 'agi_fail,s,1')
                fagi.fail()
            except Exception:
                pass


class AGID(SocketServer.ThreadingTCPServer):
    allow_reuse_address = True
    initialized = False
    request_queue_size = 20

    def __init__(self, config):
        logger.info('wazo-agid starting...')

        self.config = config
        signal.signal(signal.SIGHUP, sighup_handle)

        self.db_conn_pool = DBConnectionPool()
        self.setup()

        FastAGIRequestHandler.config = config
        SocketServer.ThreadingTCPServer.__init__(self,
                                                 (self.listen_addr, self.listen_port),
                                                 FastAGIRequestHandler)

        self.initialized = True

    def setup(self):
        if not self.initialized:
            self.listen_addr = self.config["listen_address"]
            logger.debug("listen_addr: %s", self.listen_addr)

            self.listen_port = int(self.config["listen_port"])
            logger.debug("listen_port: %d", self.listen_port)

        conn_pool_size = int(self.config["connection_pool_size"])

        db_uri = self.config["db_uri"]
        self.db_conn_pool.reload(conn_pool_size, db_uri)


class Handler(object):
    def __init__(self, handler_name, setup_fn, handle_fn):
        self.handler_name = handler_name
        self.setup_fn = setup_fn
        self.handle_fn = handle_fn
        self.lock = moresynchro.RWLock()

    def setup(self, cursor):
        if self.setup_fn:
            self.setup_fn(cursor)

    def reload(self, cursor):
        if self.setup_fn:
            if not self.lock.acquire_write():
                logger.error("deadlock detected and avoided for %r", self.handler_name)
                logger.error("%r has not be reloaded", self.handler_name)
                return
            try:
                self.setup_fn(cursor)
                logger.debug('handler %r reloaded', self.handler_name)
            finally:
                self.lock.release()

    def handle(self, agi, cursor, args):
        self.lock.acquire_read()
        try:
            with session_scope():
                self.handle_fn(agi, cursor, args)
        finally:
            self.lock.release()


def register(handle_fn, setup_fn=None):
    handler_name = handle_fn.__name__

    if handler_name in _handlers:
        raise ValueError("handler %r already registered", handler_name)

    _handlers[handler_name] = Handler(handler_name, setup_fn, handle_fn)


def sighup_handle(signum, frame):
    logger.debug("reloading core engine")
    _server.setup()

    conn = _server.db_conn_pool.acquire()
    try:
        cursor = conn.cursor()

        logger.debug("reloading handlers")
        for handler in _handlers.itervalues():
            handler.reload(cursor)

        conn.commit()
        logger.debug("finished reload")
    finally:
        _server.db_conn_pool.release(conn)


def run():
    conn = _server.db_conn_pool.acquire()
    try:
        cursor = conn.cursor()

        logger.debug("list of handlers: %s", ', '.join(sorted(_handlers.iterkeys())))

        for handler in _handlers.itervalues():
            handler.setup(cursor)

        conn.commit()
    finally:
        _server.db_conn_pool.release(conn)

    _server.serve_forever()


def init(config):
    global _server
    _server = AGID(config)
