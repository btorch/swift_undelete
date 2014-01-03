# Copyright (c) 2013 Samuel N. Merritt <sam@swiftstack.com>
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Middleware for OpenStack Swift that implements undelete functionality.

When this middleware is installed, an object DELETE request will cause a copy
of the object to be saved into a "trash location" prior to deletion.
Subsequently, an administrator can recover the deleted object.

Caveats:

 * This does not provide protection against overwriting an object. Use Swift's
   object versioning if you require overwrite protection.

 * If your account names are near the maximum length, this middleware will
   fail to create trash accounts, leaving some objects unable to be deleted.

 * If your container names are near the maximum length, this middleware will
   fail to create trash containers, leaving some objects unable to be deleted.

 * If your cluster is too full to allow an object to be copied, you will be
   unable to delete it. In extremely full clusters, this may result in a
   situation where you need to add capacity before you can delete objects.

Future work:

 * allow undelete to be enabled only for particular accounts or containers

"""


from swift.common import http, swob, wsgi


# Helper method stolen from a pending Swift change in Gerrit.
#
# If it ever actually lands, import and use it instead of having this
# duplication.
def close_if_possible(maybe_closable):
    close_method = getattr(maybe_closable, 'close', None)
    if callable(close_method):
        return close_method()


class CopyContext(wsgi.WSGIContext):
    """
    Helper class to perform an object COPY request.
    """
    def copy(self, env, destination_container, destination_object):
        """
        Perform a COPY from source to destination

        :param env: WSGI environment for a request aimed at the source
            object.
        :param destination_container: container to copy into.
            Note: this must not contain any slashes or the request is
            guaranteed to fail.
        :param destination_object: destination object name

        :returns: 3-tuple (HTTP status code, response headers,
                           full response body)
        """
        env = env.copy()
        env['REQUEST_METHOD'] = 'COPY'
        env['HTTP_DESTINATION'] = '/'.join((destination_container,
                                           destination_object))
        resp_iter = self._app_call(env)
        # The body of a COPY response is either empty or very short (e.g.
        # error message), so we can get away with slurping the whole thing.
        body = ''.join(resp_iter)
        close_if_possible(resp_iter)

        status_int = int(self._response_status.split(' ', 1)[0])
        return (status_int, self._response_headers, body)


class UndeleteMiddleware(object):
    def __init__(self, app, trash_prefix):
        self.app = app
        self.trash_prefix = trash_prefix

    @swob.wsgify
    def __call__(self, req):
        # We only want to step in on object DELETE requests
        if req.method != 'DELETE':
            return self.app
        try:
            vrs, acc, con, obj = req.split_path(4, 4, rest_with_last=True)
        except ValueError:
            # not an object request
            return self.app

        # Okay, this is definitely an object DELETE request; let's see if it's
        # one we want to step in for.
        if not self.should_save_copy(req.environ, con, obj):
            return self.app

        trash_container = self.trash_prefix + con
        copy_status, copy_headers, copy_body = CopyContext(self.app).copy(
            req.environ, trash_container, obj)
        if copy_status == 404:
            # container's not there, so we'll have to go create it first
            raise NotImplementedError("container creation")
        elif not http.is_success(copy_status):
            # other error; propagate this to the client
            return swob.Response(
                body="Error copying object to trash:\n" + copy_body,
                status=copy_status,
                headers=copy_headers)

        return self.app

    def should_save_copy(self, env, con, obj):
        """
        Determine whether or not we should save a copy of the object prior to
        its deletion. For example, if the object is one that's in a trash
        container, don't save a copy lest we get infinite metatrash recursion.
        """
        return not con.startswith(self.trash_prefix)


def filter_factory(global_conf, **local_conf):
    """
    Returns the WSGI filter for use with paste.deploy.

    Parameters in config:

    # value to prepend to the account in order to compute the trash location
    trash_prefix = ".trash-"

    """
    conf = global_conf.copy()
    conf.update(local_conf)

    trash_prefix = conf.get("trash_prefix", ".trash-")

    def filt(app):
        return UndeleteMiddleware(app, trash_prefix)
    return filt
