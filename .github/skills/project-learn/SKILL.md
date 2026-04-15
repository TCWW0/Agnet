---
name: project-learn
description: Quickly understand the basic requirements of the current project.
---
<!-- Tip: Use /create-skill in chat to generate content with agent assistance -->

# Project-Learning

## Get to know quickly

Quickly understand the design background and vision of the current project

From a macro perspective,the overall background of the project is as follows:

- This is a personal project for learning about agents and designing a minimalist agent framework.
- This project is implemented using the Python language.
- The project aims for a gradual evolution, starting with a relatively simple implementation, creating a basic version, and then iterating and improving upon it in subsequent iterations.
- The core code of the project is located in the frame directory.
- The Core directory under Frame stores the core generic code.
- The test directory under Frame stores the test code.When you need to generate files for testing, please strictly only generate them in this directory.
- The `agents` directory under `frame` stores the framework's existing simple agents built based on the core code.

## Project requirements

- The project aims to implement a basic, self-usable agent framework.
- It doesn't require a complex architecture; it needs to generate clear and readable code, avoiding obscure syntax.
- The project is currently being developed using virtual environments; any Python commands should be executed using the virtual environment specified in the .venv file.
- We don't want too many syntax warnings in a Python file. After generating a file, we need to check for static syntax warnings and resolve them, while avoiding hacky solutions like using comments.
