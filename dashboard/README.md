# CoOps Frontend

Modern React frontend for CoOps - GitHub collaboration metrics visualization platform.

## Tech Stack

- **React 19** - UI library
- **TypeScript** - Type safety
- **Vite** - Build tool and dev server
- **React Router** - Client-side routing
- **D3.js** - Data visualization
- **Tailwind CSS v4** - Styling
- **Prettier** - Code formatting
- **ESLint** - Code linting

## Project Structure

```
src/
├── components/          # Reusable UI components
│   ├── BaseFilters.tsx
│   ├── DashboardLayout.tsx
│   ├── Filter.tsx
│   ├── Graphs.tsx
│   ├── RepositoryToolbar.tsx
│   └── Sidebar.tsx
├── pages/              # Page components
│   ├── Commits.tsx     # Commit analysis page
│   ├── HomePage.tsx    # Landing page
│   ├── NotFound.tsx    # 404/fallback page
│   └── Utils.ts        # Data processing utilities
├── types/              # TypeScript type definitions
│   ├── charts.ts
│   ├── github.ts
│   └── index.ts
├── App.tsx             # Root component with routing
├── main.tsx            # Application entry point
└── index.css           # Global styles
```

## Available Scripts

### Development

```bash
npm run dev
```

Starts the development server at `http://localhost:5173`

### Build

```bash
npm run build
```

Builds the app for production to the `dist` folder.

### Format

```bash
npm run format
```

Formats all source files using Prettier.

```bash
npm run format:check
```

Checks if files are properly formatted without modifying them.

### Lint

```bash
npm run lint
```

Runs ESLint to check for code quality issues.

### Preview

```bash
npm run preview
```

Preview the production build locally.

### Deploy

```bash
npm run deploy
```

Deploys the built app to GitHub Pages.

## Routes

- `/` - Home page
- `/repos/commits` - Commit analysis with filters and visualizations
- `*` - 404/Not Found page for unimplemented routes

## Features

### Commits Page

- Repository selection (individual or all repos)
- Timeline filtering (24h, 7d, 30d, 6m, 1y, all time)
- Member filtering
- Interactive histogram showing commit activity over time
- Pie chart showing contributor distribution
- Responsive design

### Planned Features

The following routes are placeholders for future implementation:
- `/repos/issues` - Issues metrics
- `/repos/pullrequests` - Pull request analysis
- `/repos/collaboration` - Collaboration patterns
- `/repos/structure` - Repository structure analysis

## Development Notes

### GitHub Pages Deployment

The app is configured to deploy to GitHub Pages with the base path `/2025-2-Squad-01`. This is configured in:
- `vite.config.ts` - `base: "/2025-2-Squad-01"`
- `main.tsx` - `<BrowserRouter basename="/2025-2-Squad-01">`

When developing locally, you can access the app without the base path.

### Code Style

- Use Prettier for consistent formatting
- Follow component naming conventions (PascalCase)
- Add JSDoc comments to components explaining their purpose
- Keep components focused (Single Responsibility Principle)

### Adding New Pages

1. Create component in `src/pages/`
2. Add route in `src/App.tsx`
3. Update navigation components if needed
4. Document the component with JSDoc

## Browser Support

Modern browsers with ES6+ support.
