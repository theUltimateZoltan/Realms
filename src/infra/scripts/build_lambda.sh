#!/bin/bash
mkdir /tmp/lambda_dependencies
python3 -m pip install -r logic/requirements.txt -t /tmp/lambda_dependencies
cp logic/models.py /tmp/lambda_dependencies
zip -r /tmp/lambda_layer_payload.zip /tmp/lambda_dependencies/*