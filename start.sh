#!/bin/bash
cd /data1/aview/a-view
export AVIEW_MODE=test
export PYTHONPATH=/data1/aview/a-view
source .venv/bin/activate
exec python -m app.main
