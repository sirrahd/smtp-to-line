# SMTP to LINE
Relays incoming emails to [LINE messenger](https://line.me/). Inspired by [SMTP to Telegram](https://github.com/KostyaEsmukov/smtp_to_telegram).

Use it as an SMTP server for webcams, selfhosted services, development environments, and as a smarthost to receive emails as LINE notifications.

## Getting started
1. Set up your LINE developer account and channel: https://developers.line.biz/en/docs/messaging-api/getting-started/
2. Retrieve your user ID and channel access token from the channel in the [LINE developers console](https://developers.line.biz/console/) (Basic Settings->Your user ID; Messaging API-> Channel access token)
3. Run `smtp-to-line` in a Docker container:
```
docker run \
    --name smtp-to-line \
    -e SL_LINE_CHANNEL_ACCESS_TOKEN=<TOKEN> \
    -e SL_LINE_USER_ID=<ID> \
    docker.io/sirrahd/smtp-to-line
```
4. `smtp-to-line` listens for incoming SMTP traffic on port 8025

*Note: LINE has a 500 per month limit on free messages sent via its API ([see Messaging API overview](https://developers.line.biz/en/docs/messaging-api/overview/)).*

## Additional features

### Customized message template
Define a custom message template for LINE notifications with the environment variable `SL_MESSAGE_TEMPLATE`. Available variables:
- `{sender}`
- `{recipient}`
- `{subject}`
- `{text}`

*Default:* `SL_MESSAGE_TEMPLATE="{subject}\nFrom: {sender}\n\n{text}"`

### Hosting file attachments
`smtp-to-line` can extract images, attachments, and html messages from emails to the folder `/smtp-to-line/data`, which can then be hosted with a web server. Define an `SL_WEB_ROOT` to define a root URL where these files are hosted.

*Example:* `SL_WEB_ROOT="https://example.com/smtp-to-line/"`

### STARTTLS encryption
Specify the path to a `SL_SSL_CERT_FILE` and `SL_SSL_KEY_FILE` in PEM format to enable STARTTLS encryption.

Alternatively, `smtp-to-telegram` can use the first certificate in a [Traefik resolvers](https://doc.traefik.io/traefik/https/acme/) file with the `SL_TRAEFIK_CERT_PATH` environment variable.

### Authentication
By default `smtp-to-line` will accept any SMTP request and fake successful authentication if credentials are provided. To require real authentication for all requests, provide space-separated uesrnames and passwords in the `SL_AUTH` environment variable.

*Example:* `SL_AUTH="user1 password1 user2 password2"`

## Docker Compose example
These example docker-compose services enable all features and provide an nginx web server for hosting attachments.

```
  smtp-to-line:
    image: docker.io/sirrahd/smtp-to-line
    ports:
      - "587:8025"
    environment:
      SL_LINE_CHANNEL_ACCESS_TOKEN: "TOKEN"
      SL_LINE_USER_ID: "USERID"
      SL_WEB_ROOT: "http://example.com/"
      SL_SSL_CERT_FILE: "/certificates/cert.pem"
      SL_SSL_KEY_FILE: "/certificates/key.pem"
      SL_AUTH: "user1 password1 user2 password2"
    volumes:
      - "./certificates:/certificates:ro"
      - "./web:/smtp-to-line/data"
  nginx:
    image: docker.io/library/nginx
    ports: "80:80"
    volumes:
      - "./web:/usr/share/nginx/html"
```
