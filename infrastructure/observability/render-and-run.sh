#!/bin/sh
set -eu

escaped_url=$(printf '%s' "$STACKGRAPH_ALERT_WEBHOOK_URL" | sed 's/[&|]/\\&/g')
sed "s|__STACKGRAPH_ALERT_WEBHOOK_URL__|$escaped_url|g" /etc/alertmanager/alertmanager.template.yml > /tmp/alertmanager.yml
exec /bin/alertmanager --config.file=/tmp/alertmanager.yml --storage.path=/alertmanager
