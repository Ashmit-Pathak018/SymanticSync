/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        primary: {
          DEFAULT: '#315CFF',
          hover: '#2649CC',
          light: '#EBF0FF',
        },
        nav: '#111A3A',
        workspace: '#F4F6FA',
        panel: '#FFFFFF',
        border: '#D8DEEA',
        success: {
          DEFAULT: '#2D9B62',
          light: '#EAF7F0',
        },
        warning: {
          DEFAULT: '#C98A1B',
          light: '#FEF8EC',
        },
        danger: {
          DEFAULT: '#D94B5B',
          light: '#FDF2F3',
        },
        text: {
          primary: '#1A1F36',
          secondary: '#5A6075',
          muted: '#9AA0B2',
          inverse: '#FFFFFF',
        }
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        mono: ['JetBrains Mono', 'Fira Code', 'monospace'],
      },
    },
  },
  plugins: [],
}
