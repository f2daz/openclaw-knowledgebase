/**
 * Unified Theme Switcher for Jarvis Apps
 * 
 * Usage (vanilla JS / Alpine.js):
 *   ThemeSwitcher.init()           // Load saved theme on page load
 *   ThemeSwitcher.set('neon')      // Switch theme
 *   ThemeSwitcher.current()        // Get current theme name
 *   ThemeSwitcher.themes           // List available themes
 *
 * Usage (React):
 *   Import and use the useTheme hook from theme-switcher-react.ts
 */

const ThemeSwitcher = {
  STORAGE_KEY: 'jarvis-theme',
  DEFAULT_THEME: 'stealth',
  
  themes: [
    { id: 'stealth', name: 'Stealth', emoji: '🌑', description: 'Subtil & minimal' },
    { id: 'liquid-glass', name: 'Liquid Glass', emoji: '💎', description: 'Bunt & animiert' },
    { id: 'neon', name: 'Neon', emoji: '🔮', description: 'Cyberpunk Glow' },
  ],

  init() {
    const saved = localStorage.getItem(this.STORAGE_KEY) || this.DEFAULT_THEME;
    this.set(saved, false);
    return saved;
  },

  set(themeId, save = true) {
    if (!this.themes.find(t => t.id === themeId)) {
      console.warn(`Unknown theme: ${themeId}, falling back to ${this.DEFAULT_THEME}`);
      themeId = this.DEFAULT_THEME;
    }
    document.documentElement.setAttribute('data-theme', themeId);
    if (save) {
      localStorage.setItem(this.STORAGE_KEY, themeId);
    }
    // Dispatch event for frameworks to react
    window.dispatchEvent(new CustomEvent('theme-changed', { detail: { theme: themeId } }));
    return themeId;
  },

  current() {
    return document.documentElement.getAttribute('data-theme') || this.DEFAULT_THEME;
  },

  next() {
    const cur = this.current();
    const idx = this.themes.findIndex(t => t.id === cur);
    const next = this.themes[(idx + 1) % this.themes.length];
    return this.set(next.id);
  },
};

// Auto-init if loaded as script
if (typeof window !== 'undefined') {
  // Apply theme immediately to prevent flash
  const saved = localStorage.getItem('jarvis-theme') || 'stealth';
  document.documentElement.setAttribute('data-theme', saved);
}
