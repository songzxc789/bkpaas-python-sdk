# -*- coding: utf-8 -*-
"""
 * TencentBlueKing is pleased to support the open source community by making 蓝鲸智云-蓝鲸 PaaS 平台(BlueKing-PaaS) available.
 * Copyright (C) 2017-2021 THL A29 Limited, a Tencent company. All rights reserved.
 * Licensed under the MIT License (the "License"); you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at http://opensource.org/licenses/MIT
 * Unless required by applicable law or agreed to in writing, software distributed under the License is distributed on
 * an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the License for the
 * specific language governing permissions and limitations under the License.
"""
import json
import logging
from typing import Any, Dict, Optional

from requests import Response
from requests.exceptions import HTTPError, RequestException
from requests.sessions import merge_setting
from requests.structures import CaseInsensitiveDict

from bkapi_client_core.auth import BKApiAuthorization
from bkapi_client_core.base import Operation
from bkapi_client_core.config import HookEvent
from bkapi_client_core.exceptions import (
    APIGatewayResponseError,
    EndpointNotSetError,
    HTTPResponseError,
    JSONResponseError,
)
from bkapi_client_core.session import Session
from bkapi_client_core.utils import to_curl, urljoin

logger = logging.getLogger(__name__)


class RequestContextBuilder(object):
    def build(
        self,
        endpoint,  # type: str
        operation_context,  # type: Dict[str, Any]
    ):
        # type: (...) -> Dict[str, Any]
        return self.build_request_context(endpoint, **operation_context)

    def build_request_context(
        self,
        endpoint,  # type: str
        data=None,  # type: Any
        path="",  # type: str
        **request_context  # type: Dict[str, Any]
    ):
        # type: (...) -> Dict[str, Any]
        self.build_url(request_context, endpoint, path)
        self.build_data(request_context, data)

        return request_context

    def build_url(
        self,
        context,  # type: Dict[str, Any]
        endpoint,  # type: str
        path,  # type: str
    ):
        context["url"] = urljoin(endpoint, path)

    def build_data(
        self,
        context,  # type: Dict[str, Any]
        data=None,  # type: Optional[Dict[str, Any]]
    ):
        if not data:
            return

        if context["method"] in ["GET", "HEAD", "OPTIONS"]:
            params = data.copy()
            params.update(context.get("params") or {})
            context["params"] = params
        else:
            context["json"] = data


class ResponseHeadersRepresenter(object):
    """Provide useful methods for response headers"""

    def __init__(self, headers):
        self._headers = headers

    def _get_header(self, key, default=""):
        if not self._headers:
            return default

        return self._headers.get(key, default)

    @property
    def error_code(self):
        return self._get_header("X-Bkapi-Error-Code", "")

    @property
    def error_message(self):
        return self._get_header("X-Bkapi-Error-Message", "")

    @property
    def request_id(self):
        return self._get_header("X-Bkapi-Request-Id", "")

    @property
    def has_apigateway_error(self):
        # type: (...) -> bool
        """Whether it contains an error generated by the apigateway"""
        return bool(self.error_code)

    def __str__(self):
        if not self._headers:
            return ""

        return "request_id: %s, error_code: %s, %s" % (self.request_id, self.error_code, self.error_message)


class BaseClient(object):
    _build_class = RequestContextBuilder
    _reuse_session_connection = False
    name = "client"

    def __init__(
        self,
        endpoint="",  # type: str
        session=None,  # type: Optional[Session]
        name=None,  # type: Optional[str]
    ):
        self._endpoint = endpoint
        self.session = session or Session()
        self._context_builder = self._build_class()

        if name:
            self.name = name

        self.on_init()
        self.session.dispatch_hook(HookEvent.CLIENT_INITIALIZED, self)

    def get_client(self):
        return self

    def __enter__(self):
        self._reuse_session_connection = True
        return self

    def __exit__(self, *args):
        self._reuse_session_connection = False
        self.close()

    def __str__(self):
        return self.name

    def on_init(self):
        pass

    def handle_request(
        self,
        operation,  # type: Operation
        context,  # type: Dict[str, Any]
    ):
        # type: (...) -> Optional[Response]
        """Handle operation with context"""

        # you can inject extra context from hooks
        context = self.session.dispatch_hook(HookEvent.HANDLE_REQUEST_CONTEXT, context, operation=operation)
        try:
            response = self.session.handle(**self._get_request_context(operation, context))
            return self._handle_response(operation, context, response)
        except RequestException as err:
            return self._handle_exception(operation, context, err)
        finally:
            if not self._reuse_session_connection:
                # close the pooled connections to avoid connection leaks
                self.close()

    def parse_response(
        self,
        operation,  # type: Operation
        response,  # type: Optional[Response]
    ):
        # type: (...) -> Any
        try:
            return self._handle_response_content(operation, response)
        except RequestException as err:
            return self._handle_exception(operation, None, err)

    def update_headers(
        self,
        headers,  # type: Dict[str, str]
    ):
        # type: (...) -> None
        """
        Update common HTTP request headers

        :param headers: HTTP headers
        :type headers: Dict[str, str]
        """
        self.session.headers = merge_setting(headers, self.session.headers, dict_class=CaseInsensitiveDict)

    def update_bkapi_authorization(self, **auth):
        """
        Set the request authorization information

        :raises TypeError: when session.auth is not the instance of BKApiAuthorization
        """
        if self.session.auth and not isinstance(self.session.auth, BKApiAuthorization):
            raise TypeError("session auth should be BKApiAuthorization")

        if not self.session.auth:
            self.session.auth = BKApiAuthorization()

        self.session.auth.update(auth)  # type: ignore

    def set_timeout(
        self,
        timeout,  # type: float
    ):
        """
        Set common request timeout

        :param timeout: seconds to wait for the request to complete
        :type timeout: float
        """
        self.session.timeout = timeout

    def disable_ssl_verify(self):
        """
        Disable SSL certificate verification
        """
        self.session.verify = False

    def _get_endpoint(self):
        # type: (...) -> str
        return self._endpoint

    def _get_request_context(
        self,
        operation,  # type: Operation
        context,  # type: Dict[str, Any]
    ):
        # type: (...) -> Dict[str, Any]
        endpoint = self._get_endpoint()
        if not endpoint:
            raise EndpointNotSetError()

        request_context = self._context_builder.build(endpoint, context)
        logger.debug("request to %s with context %s", operation, request_context)

        return request_context

    def _handle_exception(
        self,
        operation,  # type: Operation
        context,  # Optional(type: Dict[str, Any])
        exception,  # type: Exception
    ):
        # type: (...) -> Optional[Response]
        # log exception
        if isinstance(exception, RequestException):
            response = exception.response
            response_headers_representer = ResponseHeadersRepresenter(response and response.headers)
            logger.exception(
                "request bkapi failed. status_code: %s, %s\n%s",
                response and response.status_code,
                str(response_headers_representer),
                to_curl(exception.request),
            )
        else:
            logger.exception("request operation failed. operation: %s, context: %s", operation, context)

        # handle exception
        raise exception

    def _handle_response(
        self,
        operation,  # type: Operation
        context,  # type: Dict[str, Any]
        response,  # type: Response
    ):
        # type: (...) -> Response
        response_headers_representer = ResponseHeadersRepresenter(response.headers)
        logger.debug(
            "request to %s with context %s, status_code: %s, %s\n%s",
            operation,
            context,
            response.status_code,
            str(response_headers_representer),
            to_curl(response.request),
        )

        return response

    def _handle_response_content(
        self,
        operation,  # type: Operation
        response,  # type: Optional[Response]
    ):
        if response is None:
            return None

        response_headers_representer = ResponseHeadersRepresenter(response.headers)
        if response_headers_representer.has_apigateway_error:
            raise APIGatewayResponseError(
                "Request bkapi error, %s" % response_headers_representer.error_message,
                response=response,
                response_headers_representer=response_headers_representer,
            )

        try:
            response.raise_for_status()
        except HTTPError as err:
            raise HTTPResponseError(
                str(err), response=response, response_headers_representer=response_headers_representer
            )

        try:
            return response.json()
        except (TypeError, json.JSONDecodeError):
            raise JSONResponseError(
                "The response is not a valid JSON",
                response=response,
                response_headers_representer=response_headers_representer,
            )

    def close(self):
        """Close the session"""
        self.session.close()
