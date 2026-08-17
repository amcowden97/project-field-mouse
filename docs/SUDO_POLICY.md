# Production sudo policy

Integration and release operators belong to `pfm-operators`. The policy in
`deploy/sudoers/project-field-mouse` permits only:

- the root-owned `pfm-deploy` and `pfm-rollback` entry points;
- start, stop, restart, or status for named Field Mouse units;
- `systemctl daemon-reload`;
- fixed 200-line journal reads for named Field Mouse units, including reliability
  capture;
- reboot; and
- `/usr/bin/true`, solely for noninteractive authorization testing.

It does not authorize shells, editors, arbitrary `systemctl` arguments, package
managers, file-copy commands, user management, or general root execution. Deployment
scripts are installed root-owned and are not writable by the operator or service user.

Bootstrap once from an existing administrator account:

```bash
sudo deploy/production/bootstrap-production.sh RELEASE_OPERATOR
```

The operator must start a new login session after group membership changes. Validate:

```bash
sudo -n true
sudo -n /usr/bin/systemctl status fieldmouse-dashboard.service
sudo -n /usr/bin/journalctl --no-pager -n 200 -u fieldmouse-dashboard.service
sudo -n /usr/bin/systemctl status fieldmouse-reliability.timer
sudo -n /usr/bin/systemctl start fieldmouse-reliability.service
sudo -n /usr/bin/id && echo "POLICY FAILURE" || echo "Correctly denied"
sudo -n /bin/sh -c true && echo "POLICY FAILURE" || echo "Correctly denied"
```

Always validate a candidate policy with `visudo -cf` before installation. The bootstrap
script does this and then validates the complete sudo configuration with `visudo -c`.
