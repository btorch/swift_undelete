Swift Undelete
==============

Middleware for [OpenStack Swift](https://docs.openstack.org/developer/swift/)
that implements "undelete" functionality.

When this middleware is installed, an object `DELETE` request will cause a copy
of the object to be saved into a "trash location" prior to deletion.
Subsequently, an administrator can recover the deleted object.

Caveats
-------

 * This does not provide protection against overwriting an object. Use Swift's
   object versioning if you require overwrite protection.

 * If your account names are near the maximum length, this middleware will
   fail to create trash accounts, leaving some objects unable to be deleted.

 * If your container names are near the maximum length, this middleware will
   fail to create trash containers, leaving some objects unable to be deleted.

 * If your cluster is too full to allow an object to be copied, you will be
   unable to delete it. In extremely full clusters, this may result in a
   situation where you need to add capacity before you can delete objects.

 * Requires Swift 1.12.0+, which introduced system metadata.

Enabling
--------

Add a new filter section to your proxy-server.conf:

```
[filter:swift_undelete]
use = egg:swift_undelete#undelete
trash_prefix = .trash-
trash_lifetime = 120
block_trash_deletes = no
enable_by_default = yes
```

Add the filter to the `[pipeline:main]` section:

```
[pipeline:main]
pipeline = catch_errors ... <auth middleware> swift_undelete ... proxy-server
```

By placing `swift_undelete` somewhere after auth, you avoid unnecessary
additional auth requests.

Future work
-----------

 * Move to separate account, not container, for trash. This requires Swift to
   allow cross-account `COPY` requests.

 * If `block_trash_deletes` is on, modify the `Allow` header in responses (both
   `OPTIONS` responses and any other 405 response).

Swift-Undelete is Copyright (c) 2014 SwiftStack, Inc. and licensed under the
Apache 2.0 license (see LICENSE).
