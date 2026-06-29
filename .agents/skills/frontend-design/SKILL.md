---
name: frontend-design
description: Guidelines and best practices for creating stunning, high-fidelity, and premium frontend designs using modern CSS, Glassmorphism, tailored color palettes, typography, and micro-animations.
---

# Premium Frontend Design Guidelines

This skill provides core instructions and code patterns to build web interfaces that look premium, modern, and visually striking.

## 1. Color Palettes & Contrast
Avoid browser-default primary colors (e.g., pure red, pure blue, pure green). Instead, use custom HSL or hex color mappings that feel cohesive:
* **Backgrounds:** Deep dark tones (`#020617` Slate-950, `#090d16` Navy-Dark) or clean off-whites (`#f8fafc`).
* **Accents:** Neon/pastel shades with subtle glowing effects (`#38bdf8` Neon Blue, `#10b981` Emerald, `#a78bfa` Purple).
* **Text Gradients:** Use text-clipping gradients for main headers:
  ```css
  background: linear-gradient(135deg, #38bdf8 0%, #a78bfa 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  ```

## 2. Glassmorphism
Premium cards and layouts should look layered, using translucent panels with backdrops:
```css
.premium-card {
  background: rgba(15, 23, 42, 0.35); /* Translucent navy */
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 1rem;
}
```

## 3. Typography
Avoid standard browser system fonts. Use clean Google Fonts (e.g., **Inter**, **Outfit**, or **Roboto**):
```html
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;800&display=swap" rel="stylesheet">
```
```css
body {
  font-family: 'Outfit', sans-serif;
  letter-spacing: -0.02em;
}
```

## 4. Micro-Animations & Hover Effects
Interfaces should feel responsive and interactive:
* **Transitions:** Always use smooth ease-out curves on interactive elements:
  ```css
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  ```
* **Hover Scaling:** Subtle size increase combined with a soft border highlight:
  ```css
  .interactive-element:hover {
    transform: translateY(-2px) scale(1.01);
    border-color: rgba(99, 102, 241, 0.4);
    box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.3), 
                0 0 15px rgba(99, 102, 241, 0.15);
  }
  ```

## 5. Chart Styling
* **Chart Fills:** Use custom linear gradients with low opacity (`0.4` at top to `0.0` at bottom) to represent area charts cleanly.
* **Grid lines:** Use low-contrast borders (`#1e293b`) to avoid cluttering the visualization.
