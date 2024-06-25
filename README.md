# ZDM Python WebServer

## Run Evaluation ##
```
curl -X POST "http://127.0.0.1:8000/eval" \
     -H "Content-Type: application/json" \
     -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" \
     -d '{
           "sourcedb": "MOBUAT",
           "sourcenode": "gdx7db01vm01-mgmt",
           "srcauth": "zdmauth",
           "srcarg1": "user:SVC_OCIMIG",
           "srcarg2": "identity_file:/home/zdmuser/.ssh/id_rsa",
           "srcarg3": "sudo_location:/usr/bin/sudo",
           "targetnode": "aeocidb01vn-4hja81",
           "tgtauth": "zdmauth",
           "tgtarg1": "user:opc",
           "tgtarg2": "identity_file:/home/zdmuser/.ssh/id_rsa",
           "tgtarg3": "sudo_location:/usr/bin/sudo",
           "rsp": "/home/zdmuser/migration/MOBUAT/MOBUAT.rsp",
           "sourcesyswallet": "/home/zdmuser/migration/sysWallet_11g_v2"
         }'
```
## Get Job Status ##
```
curl -X GET "http://127.0.0.1:8000/query/25" \
     -H "Authorization: Basic $(echo -n 'zdmuser:YourPassword123#_' | base64)" | jq .
```
OR
```
echo -n 'zdmuser:YourPassword123#_' | base64

curl -X GET "http://127.0.0.1:8000/query/25" \
     -H "Authorization: Basic emRtdXNlcjpZb3VyUGFzc3dvcmQxMjMjXw==" | jq .
```
