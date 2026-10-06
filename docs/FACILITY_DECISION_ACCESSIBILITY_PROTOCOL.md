# Facility Decision Integrity accessibility protocol

## Scope

This protocol applies to the five RC3.6A routes under `/examples/facility-decision`. The source gate checks semantic HTML and known high-risk accessibility regressions. It is not, by itself, a WCAG conformance claim.

## Automated source and build gates

The release must verify:

- one visible page heading and ordered section headings;
- native buttons, labels, fieldsets, legends, selects, and textareas;
- a named form with help text;
- a polite atomic status region for state changes and errors;
- no positive `tabIndex`, keyboard trap, drag-only action, or automatic time advance in learner mode;
- visible focus styling for links, buttons, checkboxes, selects, and text inputs;
- minimum button height of 44 CSS pixels in the shared button component;
- separate role routes with no in-session privilege switch;
- no autoplay or completed replay in learner projections;
- no information conveyed only by a red/green correctness label.

## Manual keyboard protocol

1. Open each route at 100%, 200%, and 400% browser zoom.
2. Use only Tab, Shift+Tab, Enter, Space, arrow keys, and Escape.
3. Confirm focus is always visible and never obscured.
4. Confirm selecting a decision moves focus to its form heading.
5. Confirm cancelling or submitting does not trap focus.
6. Complete the canonical learner path without a pointer.
7. Confirm no action requires dragging or precision movement.

## Screen-reader protocol

Run at least one Chromium-based browser with NVDA on Windows and one WebKit browser with VoiceOver on macOS/iOS when those environments are available.

Confirm:

- page title and role purpose are announced;
- the receiving brief and initial observations have a sensible reading order;
- every input has a useful accessible name;
- required fields are communicated;
- status, errors, new diagnostic results, world events, terminal status, and handoff completion are announced;
- instructor-only material is absent from learner routes;
- repeated resource and order information remains understandable outside the visual grid.

## Contrast, reflow, and motion protocol

- Measure text and non-text contrast in default, focus, disabled, caution, and critical states.
- Verify no two-dimensional scrolling at 320 CSS pixels except where a data table truly requires it.
- Verify text spacing overrides do not clip content.
- Verify `prefers-reduced-motion` removes nonessential animation.
- Verify content remains usable with CSS disabled enough to expose semantic order.

## Human-factors protocol

Representative learners and instructors must complete the safety-critical tasks in a realistic receiving-clinic exercise context. Record use errors, close calls, recovery behavior, misunderstanding of unavailable actions, and handoff omissions. Automated tests do not replace this evaluation.

## Release statement

Until the manual keyboard, assistive-technology, contrast, reflow, and representative-user protocols are completed, the release may report `AUTOMATED_SOURCE_GATES_PASS` but must report `MANUAL_ACCESSIBILITY_VALIDATION_REQUIRED` and must not claim WCAG 2.2 AA conformance.
