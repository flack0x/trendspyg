# Security Policy

## Supported Versions

Only the latest released version receives security updates. Please upgrade to
the newest release before reporting a vulnerability.

| Version        | Supported          |
| -------------- | ------------------ |
| latest (0.7.x) | :white_check_mark: |
| older          | :x:                |

## Reporting a Vulnerability

We take security seriously. If you discover a security vulnerability in trendspyg, please report it privately.

### How to Report

**Please DO NOT open a public issue for security vulnerabilities.**

Instead:

1. **Email:** Send details to ali.marodis2@gmail.com with subject "SECURITY: trendspyg vulnerability"
2. **GitHub Security Advisory:** Use GitHub's private vulnerability reporting at https://github.com/flack0x/trendspyg/security/advisories/new

### What to Include

Please provide:
- Description of the vulnerability
- Steps to reproduce the issue
- Potential impact
- Suggested fix (if you have one)
- Your contact information

### Response Timeline

- **Initial response:** Within 48 hours
- **Status update:** Within 7 days
- **Fix timeline:** Depends on severity
  - Critical: 1-3 days
  - High: 1-2 weeks
  - Medium: 2-4 weeks
  - Low: Next planned release

## Security Considerations

### Data Handling

trendspyg does not:
- Store user credentials
- Collect personal data
- Send data to third-party services (except Google Trends public endpoints)
- Execute arbitrary code from external sources

### Dependencies

We regularly monitor dependencies for known vulnerabilities using:
- GitHub Dependabot alerts
- Manual security audits

To check dependencies yourself (reads the installed environment / pyproject
directly — no requirements.txt needed):
```bash
pip install pip-audit
pip-audit
```

### Browser Automation (CSV Mode)

When using CSV download functionality:
- Selenium is used for browser automation
- Chrome/Chromium browser is required
- Downloads are saved to a specified local directory
- No data is sent to external services

**Security recommendations:**
- Keep Chrome/Chromium updated
- Only download trends from trusted geographic regions
- Review downloaded files before processing

### RSS Feed (Default Mode)

RSS mode is more secure:
- No browser automation required
- Direct HTTPS requests to Google Trends RSS
- XML parsed with the standard library, trusting the HTTPS response from Google.
  (stdlib ElementTree is not hardened against maliciously-crafted XML, so this
  path's safety rests on the Google Trends endpoint being trustworthy over TLS.)

## Best Practices for Users

1. **Keep trendspyg updated:**
   ```bash
   pip install --upgrade trendspyg
   ```

2. **Use virtual environments:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   pip install trendspyg
   ```

3. **Validate inputs:**
   - Use only validated geo codes
   - Sanitize user inputs before passing to trendspyg

4. **Review output:**
   - Check downloaded data before use
   - Be aware that trend data comes from public Google sources

## Known Limitations

- **Selenium dependency:** CSV mode requires browser automation (potential attack vector if Chrome has vulnerabilities)
- **Network requests:** RSS mode makes HTTP requests to Google (ensure network security)
- **File downloads:** CSV mode saves files locally (ensure proper permissions)

## Disclosure Policy

- Vulnerabilities will be disclosed publicly after a fix is released
- Credit will be given to reporters (unless anonymity is requested)
- Security advisories will be published on GitHub

## Security Updates

Subscribe to security updates:
- Watch this repository for security advisories
- Follow releases: https://github.com/flack0x/trendspyg/releases
- Check CHANGELOG.md for security-related fixes

## Questions?

For non-security questions, please open a regular issue.

For security concerns, email: ali.marodis2@gmail.com

Thank you for helping keep trendspyg secure! 🔒
