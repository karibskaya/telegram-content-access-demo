# Telegram Content Access Demo Bot

[Русская версия](README.ru.md)

A Python bot for temporary access to video lessons in Telegram.

The project demonstrates a working access-control mechanism for info products, online courses, private lessons, and other Telegram-based products where it is not enough to simply send a video to a user — access to the material needs to be managed after delivery.

Core idea:

```text
do not send the lesson as a disposable message
that later needs to be deleted,

but use a managed message container
that can move between states.
```

## Live Bot

The demo bot is available in Telegram:

```text
https://t.me/info_access_demo_bot
```

The bot demonstrates the main flow: placeholder video → access check → temporary lesson opening → return to placeholder by timer → repeated opening while access is active.


## What problem the bot solves

Telegram bots for info products often need to:

* open access to a lesson;
* check whether the user has permission to access it;
* show the material only when access is active;
* close access after the viewing session ends;
* offer renewal if access has expired;
* avoid cluttering the chat with repeated copies of the same material;
* avoid relying on deleting old messages.

The naive flow looks like this:

```text
send the lesson video to the user
→ wait until access expires
→ delete the message
```

This model is fragile: message deletion in Telegram has limitations and should not be the only mechanism for managing content access.

This project uses a different model:

```text
placeholder video
→ access check
→ lesson video
→ timer
→ return to placeholder
```

The material stays inside one managed message, while the bot changes its content depending on the access state.

## What the bot does

The bot demonstrates temporary access to one video lesson.

Implemented features:

* main menu;
* demo access group;
* “Enter group” button;
* “Leave group” button;
* material with a placeholder video;
* “Watch lesson” button;
* access check before showing the lesson;
* replacement of the placeholder video with the main lesson video;
* automatic return to the placeholder by timer;
* manual lesson hiding;
* access denial when the user has no access;
* renewal prompt;
* admin command for getting video `file_id`;
* admin command protection through `ADMIN_USER_ID`;
* Docker deployment;
* configuration through environment variables.

## Main flow

### User with access

```text
/start
→ Enter group
→ Open material
→ bot shows the placeholder video
→ Watch lesson
→ bot checks access
→ placeholder is replaced with the lesson
→ timer starts
→ after the timer expires, the lesson returns to the placeholder
```

### User without access

```text
/start
→ Open material
→ bot shows the placeholder video
→ Watch lesson
→ bot checks access
→ access is missing
→ lesson is not shown
→ bot offers access renewal
```

## State model

### User access states

```text
NO_ACCESS  — no access
HAS_ACCESS — access is active
```

### Material states

```text
LOCKED  — material is locked, placeholder is shown
OPENED  — material is open, lesson is shown
EXPIRED — viewing session has ended, placeholder is shown again
```

## Why a placeholder video is used

The placeholder video is the safe state of the material.

The user sees that the lesson exists, but the actual content is not open. When access is confirmed, the bot replaces the placeholder with the main lesson video. When the session ends, the bot returns the material back to the placeholder.

This approach makes it possible to:

* avoid sending a new lesson every time;
* avoid deleting old messages;
* manage access through message state;
* provide a clear user interface;
* add access renewal to the same flow.

## Commands

```text
/start
```

Opens the main menu.

```text
/whoami
```

Shows the current user’s `user_id` and `chat_id`.

Used to configure the administrator.

```text
/upload
```

Admin command for uploading videos and getting Telegram `file_id`.

Available only to the user whose `user_id` is set in the `ADMIN_USER_ID` environment variable.

## Environment variables

Configuration example is available in `.env.example`.

```env
# Telegram bot token from BotFather
BOT_TOKEN=

# Telegram user_id of the admin
ADMIN_USER_ID=

# Telegram file_id of the placeholder video
PLACEHOLDER_VIDEO_ID=

# Telegram file_id of the lesson video
LESSON_VIDEO_ID=

# Lesson access duration in seconds
# Max: 172740 seconds = 47 hours 59 minutes
LESSON_TTL_SECONDS=30
```

### BOT_TOKEN

Telegram bot token received from BotFather.

Must not be stored in the repository.

### ADMIN_USER_ID

Telegram `user_id` of the administrator.

The administrator can send videos to the bot and receive their `file_id`.

### PLACEHOLDER_VIDEO_ID

Telegram `file_id` of the placeholder video.

This video is shown when the lesson is locked, unavailable, or when the viewing session has ended.

### LESSON_VIDEO_ID

Telegram `file_id` of the main lesson video.

This video is shown only to a user with active access.

### LESSON_TTL_SECONDS

Duration of the open viewing session in seconds.

After this time expires, the bot automatically returns the message to the placeholder video.

Maximum value:

```env
LESSON_TTL_SECONDS=172740
```

This equals 47 hours and 59 minutes.

## Where videos are stored

Videos are not stored in the repository and are not uploaded to the Docker container.

The flow is:

```text
admin sends a video to the bot
→ Telegram stores the media
→ bot returns file_id
→ file_id is added to environment variables
→ bot uses file_id to send and edit videos
```

Advantages:

* videos do not get into GitHub;
* the container stays lightweight;
* no separate storage is required;
* media files do not need to be stored on the server;
* the bot works with Telegram-hosted media.

Important: `file_id` should be received for the specific bot. If a new Telegram bot is created, the videos need to be sent to that bot again to get new `file_id` values.

## How to configure videos

1. Start the bot.
2. Run the command:

```text
/whoami
```

3. Copy `user_id`.
4. Add it to the environment variable:

```env
ADMIN_USER_ID=your_telegram_user_id
```

5. Restart the container.
6. Run the command:

```text
/upload
```

7. Send the placeholder video to the bot.
8. Copy the received `file_id` into the variable:

```env
PLACEHOLDER_VIDEO_ID=
```

9. Send the main lesson video to the bot.
10. Copy the received `file_id` into the variable:

```env
LESSON_VIDEO_ID=
```

11. Restart the container.

After that, the bot is ready for testing the main flow.

## Local run

Create a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Set environment variables:

```bash
export BOT_TOKEN="your_bot_token"
export ADMIN_USER_ID="your_telegram_user_id"
export PLACEHOLDER_VIDEO_ID="placeholder_file_id"
export LESSON_VIDEO_ID="lesson_file_id"
export LESSON_TTL_SECONDS=30
```

Run the bot:

```bash
python main.py
```

## Docker run

Build the image:

```bash
docker build -t telegram-content-access-demo .
```

Run the container:

```bash
docker run --rm \
  -e BOT_TOKEN="your_bot_token" \
  -e ADMIN_USER_ID="your_telegram_user_id" \
  -e PLACEHOLDER_VIDEO_ID="placeholder_file_id" \
  -e LESSON_VIDEO_ID="lesson_file_id" \
  -e LESSON_TTL_SECONDS=30 \
  telegram-content-access-demo
```

## Deployment

The project is designed for deployment in a Docker-compatible environment.

The current version works through long polling, so the container must be continuously running.

General flow:

```text
GitHub repository
→ Dockerfile
→ build pipeline
→ Docker image
→ running container
→ environment variables
→ Telegram bot
```

## Project structure

```text
telegram-content-access-demo/
  main.py
  requirements.txt
  Dockerfile
  .dockerignore
  .gitignore
  .env.example
  README.md
  README.ru.md
  docs/
    analytical-case.en.md
    analytical-case.ru.md
```

## Architecture

```text
Telegram user
→ Telegram Bot API
→ Python bot
→ in-memory state
→ editable media message
```

In the current version, state is stored in process memory:

```python
access_users
latest_material_message
material_states
```

### access_users

Users with active demo access.

### latest_material_message

The latest material message for a `chat_id` + `user_id` pair.

### material_states

Current state of the material message.

## Current limitations

The current implementation demonstrates the temporary access mechanism for one video lesson.

In the demo version:

* there is one material;
* there is no database;
* access state is stored in memory;
* state is reset when the container restarts;
* timers are stored in memory;
* the “Renew access” button demonstrates the flow, but is not connected to payment.

These limitations do not prevent testing the core mechanism: the bot opens the lesson only when access is active and automatically returns the material to the placeholder after the viewing session ends.

## Practical value

The approach solves one of the common problems of Telegram products: how to temporarily open access to a material and then close it without deleting the message.

Instead of this flow:

```text
send video → delete message later
```

the bot uses this flow:

```text
placeholder → access check → lesson → timer → placeholder
```

This gives several practical advantages:

* the user does not receive a permanent copy of the lesson in the chat;
* the chat is not cluttered with repeated sends of the same material;
* the material stays inside one managed message;
* access can be checked before every opening;
* after the session ends, the user sees a clear locked state;
* access renewal can be built into the same flow;
* the mechanism can be used for paid lessons, webinar recordings, bonuses, and temporary materials.

## Suitable use cases

The mechanism is suitable for Telegram bots that serve:

* online courses;
* private lessons;
* paid webinar recordings;
* temporary access to materials;
* access renewals;
* lesson previews;
* bonus materials after payment;
* private clubs and groups;
* info products with limited viewing time.

## What the project demonstrates

The project demonstrates a working pattern for managing access to Telegram content:

* the material is not deleted, but moved between states;
* access is checked before opening the lesson;
* the lesson video temporarily replaces the placeholder;
* after the timer expires, the message returns to the locked state;
* media files are not stored in the repository or container;
* settings are moved to environment variables;
* the bot is deployed as a Docker container.

## Tech stack

* Python
* python-telegram-bot
* Telegram Bot API
* Docker
* GitHub
* Docker-compatible hosting
