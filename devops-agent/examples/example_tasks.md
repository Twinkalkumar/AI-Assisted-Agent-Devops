# Example tasks

```bash
python main.py "Design a Kubernetes architecture from scratch for a 3-tier app \
(frontend, backend API, Postgres) and generate the manifests to deploy it \
(namespace, deployments, services, ingress, HPA)."

python main.py "Create a GitHub Actions workflow that runs tests on every PR \
and deploys to production on merge to main via kubectl."

python main.py "Generate a shell script that backs up a Postgres database \
to S3 on a cron schedule."

python main.py "Generate a PowerShell script that checks disk space on \
Windows servers and emails an alert if free space drops below 10%."
```

Enable the `run_command` tool in `config/config.yaml` if you also want the agent
to execute what it generates (e.g. `kubectl apply -f ...`), not just write files.
