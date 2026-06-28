---
name: code-review-skill
description: This skill reviews code changes and provides feedback on potential issues, improvements, and best practices.
---

Perform a code review on the provided code changes. Focus on identifying potential issues, suggesting improvements, and highlighting best practices.

### Code Review Process

#### 1. Does the app run?
1. Ensure that the application runs without errors after the changes. Check for any runtime exceptions or issues during startup.
2. Verify that the `JournalWatcherService` starts correctly in a separate thread and that it is able to monitor the journal files as expected. You will need probably to create dummy journal files in the expected directory to test this functionality.

#### 2. Are tests passing?
1. Run the test suite to ensure that all tests pass after the changes. If any tests fail, investigate the cause and note the issues.
2. Check if the tests cover the new functionality introduced in the changes. If not, note adding new tests to cover these cases.

#### 3. Is the code clean and maintainable?
1. Check for any code smells, such as long methods, large classes, or duplicated code. Refactor if necessary to improve readability and maintainability.
2. Is ruff okay?
3. Does it follow DDD, SOLID, and other best practices? Ensure that the code adheres to these principles and suggest improvements if needed.
4. The crucial thing is dependency inversion, is there any coupling? Identify any areas where the code could be refactored to reduce coupling and improve modularity.

#### 4. Are there any potential bugs or issues?
1. Look for any potential bugs or issues in the code changes. This could include logic errors, incorrect handling of edge cases, or potential performance issues.
2. Any edge cases or race conditions that could cause problems in a multi-threaded environment? Identify any areas where the code could be improved to handle these cases more effectively.

#### 5. Final report
1. Summarize the findings from the code review, including any issues, improvements, and best practices identified.
2. Provide recommendations for addressing any issues or implementing improvements.
3. Highlight any areas of the code that are particularly well-written or follow best practices.

### Important Note
- If the code looks good and there are no issues, please explicitly state that the code is clean, maintainable, and follows best practices.
- Do not search menacingly for issues; if the code is good, acknowledge it.