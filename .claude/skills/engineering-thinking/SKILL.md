---
name: engineering-thinking
description: Load and apply engineering thinking principles to code, focusing on simplicity, minimalism, and avoiding overengineering. Load when you work with any code within the repository.
---

1. Make requirements less dumb - before you proceed with coding, ensure the requirements are clear, simple, and necessary. Super simple steps

<example>
User wants to add dedicated keybind for STT, there probably goes UI, registering hotkeys... lifecycle, queue for STT service.
Lets break it down to simple steps:
1. User presses a key dedicated for that from config
2. STT starts listening
3. User speaks
4. User button presses up to stop STT
5. STT stops listening
6. Some callback goes here

This is my line of work, what happens next is not my part

Lets propose that to user as a simple step-by-step plan in concise form, i am not a Tolkien
</example>

2. Try very hard to delete the part or process. Ruthlessly try to delete some part wont break the main use-case. Threading? Maybe it's not needed at all.


3. Simplify and test - you did some work and can test it? Test it. Then ensure that user could also test it. Every work you do should be verifable by developer, BY HAND. There is nothing worse than code from agent that human not tested. Give it to test before you write unit tests. Maybe you did absolutely shit job so your imagined unit tests wont be even needed and had to be rewritten anyway.



Refer to references/brilliant_examples.md for concrete examples of applying these principles.

