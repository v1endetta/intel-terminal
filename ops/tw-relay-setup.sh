set -euo pipefail
trap 'echo "!!! STOPPED at line $LINENO: $BASH_COMMAND" >&2' ERR
P=intel-vault-510704; RG=asia-east1; B=$P-vault; SA=intel-writer@$P.iam.gserviceaccount.com
gcloud config set project $P >/dev/null
echo "== 1/5 開啟排程服務"
gcloud services enable cloudscheduler.googleapis.com run.googleapis.com
echo "== 2/5 部署台灣抓取站（asia-east1 彰化，每次執行都讀 GitHub 上最新版 ops/tw_relay.py）"
CODE="import urllib.request as u;exec(u.urlopen('https://raw.githubusercontent.com/v1endetta/intel-terminal/main/ops/tw_relay.py').read())"
gcloud run jobs deploy tw-relay --image=docker.io/library/python:3.12-slim --region=$RG --service-account=$SA \
  --set-env-vars=BUCKET=$B --command=python --args="^@^-c@$CODE" \
  --task-timeout=240 --max-retries=0 --cpu=1 --memory=1Gi --quiet
gcloud run jobs delete tw-probe --region=$RG --quiet >/dev/null 2>&1 || true
echo "== 3/5 授權排程器啟動它"
gcloud run jobs add-iam-policy-binding tw-relay --region=$RG --member=serviceAccount:$SA --role=roles/run.invoker --format=none
echo "== 4/5 設定每 5 分鐘一次"
URI="https://run.googleapis.com/v2/projects/$P/locations/$RG/jobs/tw-relay:run"
if gcloud scheduler jobs describe tw-relay-5min --location=$RG >/dev/null 2>&1; then
  gcloud scheduler jobs update http tw-relay-5min --location=$RG --schedule="*/5 * * * *" --time-zone=Asia/Taipei --uri="$URI" --http-method=POST --oauth-service-account-email=$SA --oauth-token-scope=https://www.googleapis.com/auth/cloud-platform --format=none
else
  gcloud scheduler jobs create http tw-relay-5min --location=$RG --schedule="*/5 * * * *" --time-zone=Asia/Taipei --uri="$URI" --http-method=POST --oauth-service-account-email=$SA --oauth-token-scope=https://www.googleapis.com/auth/cloud-platform --format=none
fi
echo "== 5/5 先手動跑一次（約 1 分鐘）"
gcloud run jobs execute tw-relay --region=$RG --wait
sleep 15
gcloud logging read 'resource.type="cloud_run_job" AND resource.labels.job_name="tw-relay" AND textPayload:"RELAY"' --freshness=15m --limit=5 --format='value(textPayload)'
echo "=====DONE====="
