"""Keep Supervisor credentials on the original authenticated request."""

from urllib.request import HTTPRedirectHandler, build_opener


class RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


open_core = build_opener(RejectRedirects()).open
