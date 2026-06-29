---
name: ui-ux-pro-max
description: Pro-level UI/UX guidelines for creating modern, high-fidelity interfaces with skeleton loaders, custom scrollbars, responsive layouts, empty states, and fluid transitions.
---

# UI/UX Pro Max Guidelines

This skill extends the frontend design guidelines with professional interaction patterns, structural layouts, and polished states.

## 1. Skeleton Loading States
Never show raw blank screens or blocky loading spinners for asynchronous data. Always use animated pulse skeletons that mimic actual component shapes:

```css
@keyframes pulse-light {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.skeleton-pulse {
  animation: pulse-light 1.8s cubic-bezier(0.4, 0, 0.6, 1) infinite;
  background-color: rgba(30, 41, 59, 0.6); /* Slate-800 equivalent */
  border-radius: 0.375rem;
}
```

## 2. Custom Scrollbars
Standard browser scrollbars ruin premium dark layouts. Inject custom, low-contrast scrollbars for grids and containers:

```css
/* Custom scrollbar track */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

::-webkit-scrollbar-track {
  background: rgba(15, 23, 42, 0.05);
}

/* Custom scrollbar thumb */
::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.2); /* Low contrast slate */
  border-radius: 10px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.4);
}
```

## 3. Empty States with Depth
Empty states should not just say "No data." Design them with visual hierarchy, supportive iconography (using Lucide icons with customized sizing), and clear explanatory micro-copy:

```html
<div class="flex flex-col items-center justify-center p-8 text-center border border-dashed border-slate-800 rounded-2xl bg-slate-950/20">
  <div class="p-3 bg-indigo-500/10 rounded-full border border-indigo-500/20 text-indigo-400">
    <SearchIcon class="w-6 h-6" />
  </div>
  <h3 class="mt-4 text-sm font-semibold text-slate-200">No matching returns found</h3>
  <p class="mt-1 text-xs text-slate-500 max-w-xs">Adjust your search parameters or check if different filters are applied.</p>
</div>
```

## 4. Interactive Feedback & Active States
Buttons and interactive items must feel mechanical and tactile. Always add `:active` scale reduction:

```css
.btn-tactile {
  transition: all 0.15s cubic-bezier(0.4, 0, 0.2, 1);
}

.btn-tactile:active {
  transform: scale(0.97); /* Physical click sensation */
}
```

## 5. Tooltips and Popovers
Avoid standard HTML titles. Design lightweight CSS tooltips for compact metrics:

```css
.tooltip-trigger {
  position: relative;
}

.tooltip-trigger::after {
  content: attr(data-tooltip);
  position: absolute;
  bottom: 125%;
  left: 50%;
  transform: translateX(-50%);
  padding: 0.35rem 0.6rem;
  background: #0f172a;
  border: 1px solid #1e293b;
  color: #e2e8f0;
  font-size: 10px;
  border-radius: 4px;
  white-space: nowrap;
  opacity: 0;
  pointer-events: none;
  transition: opacity 0.2s ease-in-out;
  box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1);
}

.tooltip-trigger:hover::after {
  opacity: 1;
}
```
