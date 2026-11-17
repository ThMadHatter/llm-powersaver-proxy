# Test d'integrazione SSH

I test sono opt-in e operano su un host reale con systemd. Installano l'agent in `observe_only=true`, quindi non eseguono poweroff.

Prerequisiti sul target: Proxmox/Debian, Python 3.11+, `systemctl`, `curl`, `tar`, accesso SSH root con chiave e senza password.

```bash
make test-integration-ssh \
  SSH_TEST_HOST=192.168.1.50 \
  SSH_TEST_USER=root \
  SSH_TEST_PORT=22
```

Copertura:

1. trasporto reale `scp` e comando `ssh`;
2. installazione systemd e health check;
3. autenticazione `/status`;
4. secondo deploy e cambio release;
5. deploy intenzionalmente guasto e verifica del rollback alla release precedente.

La porta predefinita dei test e `18765`, separata dalla porta normale `8765`. Si puo cambiare con `SSH_TEST_AGENT_PORT`.
