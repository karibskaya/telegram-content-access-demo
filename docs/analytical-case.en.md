# Analytical Case: Temporary Access to Telegram Video Lessons

[Русская версия](analytical-case.ru.md)

## 1. Solution Summary

This case describes a temporary access mechanism for a video lesson in a Telegram bot.

The goal is to show a paid or restricted material to the user only while access is active, and then return the material to a closed state after the viewing session ends.

The solution is not based on deleting the video after it has been sent. Instead, it uses a managed message container:

```text
placeholder video
→ access check
→ video lesson
→ timer
→ placeholder video
```

The user sees one material, while its content changes depending on the access state.

## 2. Where the Problem Comes From

Telegram is often used as the main platform for digital education products:

* online courses;
* private lessons;
* webinar recordings;
* paid communities;
* bonus materials;
* temporary access products.

In these products, the bot is usually responsible not only for communication, but also for delivering materials. The user presses a button, passes an access check, and receives a video, link, file, or lesson directly in Telegram.

In practice, a problem appears quickly: if the material has already been sent to the user in chat, it becomes part of the chat history. Disabling the bot, deleting the bot, renaming the bot, or stopping the scenario does not take the already sent material back.

So access control cannot be based only on this logic:

```text
if access is active — send the material
if access is not active — do not send it again
```

The main risk appears after the first delivery: the material is already with the user.

## 3. Why the “Send the Material as a Message” Model Does Not Work

The most common mistake in Telegram products is assuming that access can be controlled through messages that have already been sent.

The naive flow looks like this:

```text
user paid for access
→ bot sent the video lesson to the chat
→ access expired
→ bot should delete or edit the old message
```

The problem is that bots have a limited window for managing already sent messages. After that, access logic cannot reliably depend on “we will delete it later” or “we will edit it later”.

If the material has already been sent to the user as a separate message, it has become part of the chat history. Deleting the bot, stopping the scenario, changing the logic, or ending the tariff does not take that material back.

For digital education products, this is critical: access may be sold for a month, six months, a year, or renewed several times. This means the mechanism must work not only during the first hours after delivery, but throughout the whole lifecycle of the product.

## 4. The Real Business Pain

When a digital product is built inside a Telegram bot, the bot often becomes the main product interface:

```text
buy access
→ open the lesson
→ return to the material later
→ renew access
→ open the lesson again
```

In this model, sending a video once is not enough.

The business needs to:

* check access before every material opening;
* avoid leaving the lesson open forever after the first delivery;
* support access renewals;
* show the user a clear closed state when access has expired;
* avoid creating multiple copies of the same video in the chat;
* avoid relying on manual deletion of old messages;
* keep control over the material after a month, six months, or several renewals.

So the task is not “send a video”. The task is to make the material manageable.

## 5. Core Idea of the Solution

The solution changes the unit of control.

Instead of this model:

```text
lesson = sent video message
```

it uses this model:

```text
lesson = managed entry point to the material
```

The user does not see the lesson itself as a permanent delivery. Instead, the user sees a placeholder video: the safe state of the material.

When the user presses “Watch lesson”, the bot checks the current access state.

If access is active, the material opens.

If access is not active, the lesson is not shown and the user receives a renewal scenario.

After the viewing session ends, the material returns to the placeholder.

## 6. Why This Works for Any Access Duration

The mechanism does not depend on when the user first received the material: today, a month ago, or six months ago.

Access is checked not when the video is first sent, but when the user attempts to open the lesson.

This gives the main advantage:

```text
access can be renewed or revoked through the user state,
not through an attempt to delete an old message with content.
```

If the user renews access, they press “Watch lesson” again and pass the access check. At the same time, `LESSON_TTL_SECONDS` limits not the user’s overall access period, but the duration of one open viewing session.

After the timer expires, the bot returns the message to the placeholder and shows the “Watch lesson again” button. If the user still has active access, pressing the button again opens the lesson and starts a new timer. If access has already expired, the bot does not show the lesson and offers renewal.

This separates two different concepts:

```text
user access period
≠
duration of one viewing session
```

A user can have access for a month or six months, while the lesson itself still opens temporarily each time and returns to the placeholder after the viewing session ends.

If access has expired, the user sees the placeholder and a renewal offer.

This scenario is especially important for digital education businesses: it makes it possible to sell not only initial access, but also renewals, without rebuilding material delivery and without relying on deleting old messages.

## 7. How the Prototype Works

The prototype implements one material:

* placeholder video;
* video lesson;
* “Watch lesson” button;
* access check;
* timer;
* return to placeholder;
* renewal offer when access is missing.

A demo access group is used to test the scenario:

* “Enter group” imitates active access;
* “Leave group” imitates lack of access.

This makes it possible to test the mechanism without payment integration, database, or external CRM.

## 8. User Scenario with Access

```text
/start
→ Enter group
→ Open material
→ bot shows the placeholder video
→ Watch lesson
→ bot checks access
→ placeholder is replaced with the video lesson
→ timer starts
→ after the timer expires, the video lesson is replaced with the placeholder
→ the “Watch lesson again” button appears
→ if access is still active, the user can open the lesson again
```

Result: the user sees the lesson temporarily within one viewing session. After the session ends, the material is closed again, but if access is active, it can be opened again.

## 9. User Scenario Without Access

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

Result: the user does not receive the video lesson, but sees a clear state and the next step.

## 10. Access States

The user has two states:

```text
NO_ACCESS  — no access
HAS_ACCESS — access is active
```

In the prototype, these states are switched with the “Enter group” and “Leave group” buttons.

In a real product, the access source can be anything:

* payment;
* subscription;
* tariff;
* group membership;
* manual access grant;
* promo code;
* access by user segment.

The specific access source does not matter for the mechanism itself. The bot only needs an answer to one question: can this user open the material right now?

## 11. Material States

The material has three states:

```text
LOCKED  — placeholder is shown
OPENED  — lesson is shown
EXPIRED — viewing session has ended, placeholder is shown again
```

These states make it possible to describe the material behavior independently of a specific business model.

## 12. State Transitions

```text
open_material
→ create a message with the placeholder
→ state LOCKED

watch_lesson with active access
→ replace placeholder with lesson
→ state OPENED
→ start timer

watch_lesson without access
→ keep placeholder
→ show renewal offer

watch_lesson from EXPIRED with active access
→ replace placeholder with lesson again
→ state OPENED
→ start a new timer

expire_lesson
→ replace lesson with placeholder
→ state EXPIRED
→ show the “Watch lesson again” button

hide_lesson
→ replace lesson with placeholder
→ state LOCKED

leave_group
→ remove access
→ if the lesson is open, return the placeholder
```

## 13. Role of the Placeholder Video

The placeholder video is a key part of the mechanism.

It is not just a decorative element, but the safe state of the material.

The placeholder solves several tasks at once:

* shows the user that the material exists;
* does not reveal the lesson itself;
* provides a place for the “Watch lesson” button;
* makes it possible to keep the same container;
* gives the user a clear interface after access ends;
* makes it possible to include a renewal offer.

Without the placeholder, the bot falls back to the model of “send the lesson as a separate message”.

## 14. Working with Video

Videos are not stored in the repository and are not uploaded to the application container.

Flow:

```text
admin sends a video to the bot
→ Telegram stores the media
→ bot returns file_id
→ file_id is added to environment variables
→ bot uses file_id to send and edit videos
```

The prototype uses at least two videos:

* placeholder video;
* main video lesson.

This approach simplifies deployment and does not require a separate media storage.

## 15. Viewing Time Limit

The open session duration is configured through an environment variable:

```env
LESSON_TTL_SECONDS=30
```

Maximum value:

```env
LESSON_TTL_SECONDS=172740
```

This equals 47 hours and 59 minutes.

The limit keeps the mechanism focused on temporary access to the material instead of turning it into permanent lesson delivery through a single message.

## 16. What Is Implemented in the Bot

The current version implements:

* bot start through `/start`;
* main menu;
* access imitation through buttons;
* material opening;
* placeholder video sending;
* access check;
* replacing the placeholder with the lesson;
* returning to the placeholder by timer;
* manual lesson hiding;
* denial when access is missing;
* renewal offer;
* admin command `/whoami`;
* admin command `/upload`;
* receiving video `file_id`;
* admin command protection through `ADMIN_USER_ID`;
* configuration through environment variables;
* Docker container launch.

## 17. Solution Boundaries

The prototype demonstrates the mechanism of managed access to Telegram content.

It is not tied to a specific school, course, CRM, payment system, or mailing platform.

This is important: different digital products have different sales processes, different tariffs, different access delivery methods, and different user accounting requirements.

That is why this case does not describe a universal production architecture “for everyone”. Such an architecture does not exist without the context of a specific business.

This case shows a separate working mechanism that can be embedded into different Telegram products.

## 18. Practical Value

The mechanism is useful when a Telegram bot is used as the main interface for content access.

It helps to:

* avoid leaving the lesson open after the viewing session ends;
* avoid building access control on message deletion;
* make repeated material opening manageable;
* show the user a closed state instead of an error;
* embed access renewal into a clear scenario;
* reduce manual admin work;
* separate access checking from video delivery;
* use the same pattern for different materials.

## 19. Suitable Products

The approach can be used for:

* online courses in Telegram;
* private lessons;
* webinar recordings;
* paid reviews or breakdowns;
* temporary bonuses;
* materials after payment;
* access renewals;
* private clubs;
* mini-courses;
* Telegram funnels with paid content.

## 20. Why This Is Not Just “a Bot with Video”

The value of the solution is not that the bot sends a video.

A regular bot can also send a video by button.

The value is in a different control model:

```text
the material has a state,
and the user receives access only through a verified state transition.
```

This turns content delivery into a managed scenario:

* who can open it;
* when they can open it;
* for how long;
* what happens after access ends;
* what next step the user sees.

## 21. Result

The project shows a working way to manage temporary access to Telegram video lessons without relying on deleting old messages.

Core idea:

```text
do not delete delivered content,
but manage the state of the message
where this content appears.
```

For digital education businesses built on Telegram bots, this solves one of the key pain points: how to show paid or restricted materials inside Telegram while keeping control over access after the first delivery.
