#!/bin/sh
set -eu

mc alias set local http://object-storage:9000 "$STACKGRAPH_OBJECT_STORE_ACCESS_KEY" "$STACKGRAPH_OBJECT_STORE_SECRET_KEY"
mc mb --ignore-existing --with-lock "local/$STACKGRAPH_EVIDENCE_S3_BUCKET"
mc version enable "local/$STACKGRAPH_EVIDENCE_S3_BUCKET"
mc retention set --default GOVERNANCE "${STACKGRAPH_EVIDENCE_RETENTION_DAYS}d" "local/$STACKGRAPH_EVIDENCE_S3_BUCKET"
