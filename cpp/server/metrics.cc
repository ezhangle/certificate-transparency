#include "server/metrics.h"

#include <cstring>
#include <evhttp.h>
#include <sstream>

#include "monitoring/registry.h"

using cert_trans::Registry;
using std::ostringstream;
using std::strncmp;

namespace cert_trans {
namespace {

const char kPrometheusProtoContentType[] =
    "application/vnd.google.protobuf;"
    "proto=io.prometheus.client.MetricFamily;encoding=delimited";
const size_t kPrometheusProtoContentTypeLen =
    std::strlen(kPrometheusProtoContentType);

}  // namespace


void ExportPrometheusMetrics(evhttp_request* req) {
  if (evhttp_request_get_command(req) != EVHTTP_REQ_GET) {
    evhttp_send_reply(req, HTTP_BADMETHOD, /*reason*/ nullptr,
                      /*databuf*/ nullptr);
    return;
  }
  ostringstream oss;
  const char* req_accept(
      evhttp_find_header(evhttp_request_get_input_headers(req), "Accept"));
  if (req_accept &&
      std::strncmp(req_accept, kPrometheusProtoContentType,
                   kPrometheusProtoContentTypeLen) == 0) {
    evhttp_add_header(evhttp_request_get_output_headers(req), "Content-Type",
                      kPrometheusProtoContentType);
    Registry::Instance()->Export(&oss);
  } else {
    evhttp_add_header(evhttp_request_get_output_headers(req), "Content-Type",
                      "text/html");
    Registry::Instance()->ExportHTML(&oss);
  }

  evbuffer_add(evhttp_request_get_output_buffer(req), oss.str().data(),
               oss.str().size());
  evhttp_send_reply(req, HTTP_OK, /*reason*/ nullptr, /*databuf*/ nullptr);
}


}  // namespace cert_trans
