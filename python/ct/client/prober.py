import gflags
import logging
import threading
import time

FLAGS = gflags.FLAGS

gflags.DEFINE_integer("probe_frequency_secs", 10*60,
                      "How often to probe the logs for updates")

from ct.client import log_client
from ct.client import monitor
from ct.client import state
from ct.crypto import merkle
from ct.crypto import verify
from twisted.internet import reactor
from twisted.web import client as twisted_client

class ProberThread(threading.Thread):
    """A prober for scheduled updating of the log view."""
    def __init__(self, ct_logs, db, cert_db, temp_db_factory, monitor_state_dir,
                 agent=None, state_keeper_class=None):
        """Initialize from a CtLogs proto."""
        threading.Thread.__init__(self)

        self.__monitors = []
        self.__db = db
        if not agent:
            agent = twisted_client.Agent(reactor)
        if not state_keeper_class:
            state_keeper_class = state.StateKeeper

        for log in ct_logs.ctlog:
            if not log.log_server or not log.log_id or not log.public_key_info:
                raise RuntimeError("Cannot start monitor: log proto has "
                                   "missing or empty fields: %s" % log)

            temp_db = temp_db_factory.create_storage(log.log_server)
            client = log_client.AsyncLogClient(agent,
                                               log.log_server,
                                               temp_db)
            hasher = merkle.TreeHasher()
            verifier = verify.LogVerifier(log.public_key_info,
                                          merkle.MerkleVerifier(hasher))
            state_keeper = state_keeper_class(FLAGS.monitor_state_dir +
                                             "/" + log.log_id)
            log_key = db.get_log_id(log.log_server)
            self.__monitors.append(monitor.Monitor(client, verifier, hasher, db,
                                                   cert_db, log_key,
                                                   state_keeper))
        self.__last_update_start_time = 0
        self.__stopped = False

    def __repr__(self):
       return "%r(%r)" % (self.__class__.__name__, self.__monitors)

    def __str__(self):
       return "%s(%s)" % (self.__class__.__name__, self.__monitors)

    def _log_probed_callback(self, succeded, monitor):
        if succeded:
            logging.info("Data for %s updated: latest timestamp is %s" %
                         (monitor.servername,
                          time.strftime("%c", time.localtime(
                            monitor.data_timestamp/1000))))
        else:
            logging.error("Failed to update data for %s: latest timestamp "
                          "is %s" % (monitor.servername,
                                     time.strftime("%c", time.localtime(
                            monitor.data_timestamp/1000))))
        self.__probed += 1
        if self.__probed == len(self.__monitors):
            self._all_logs_probed()

    def _all_logs_probed(self):
        logging.info("Probe loop completed in %d seconds" %
                     (time.time() - self.__start_time))
        sleep_time = max(0, self.__start_time +
                         FLAGS.probe_frequency_secs - time.time())
        logging.info("Next probe loop in: %d seconds" % sleep_time)
        reactor.callLater(sleep_time, self.probe_all_logs)


    def probe_all_logs(self):
        logging.info("Starting probe loop")
        self.__start_time = time.time()
        self.__probed = 0
        """Loop through all logs in the list and check for updates."""
        for monitor_ in self.__monitors:
            monitor_result = monitor_.update()
            monitor_result.addCallback(self._log_probed_callback, monitor_)

    def run(self):
        reactor.callLater(0, self.probe_all_logs)
        reactor.run(installSignalHandlers=0)

    def stop(self):
        reactor.stop()
