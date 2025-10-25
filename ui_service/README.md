# UI Service - Next.js Chat Interface

Modern chat interface for the gRPC LLM Agent built with Next.js 14, TypeScript, Tailwind CSS, and shadcn/ui.

## Features

- 🎨 Beautiful, responsive UI with Tailwind CSS
- 💬 Real-time chat interface
- 📝 Markdown rendering with syntax highlighting
- 🎭 Light/Dark mode support
- ⚡ Fast and optimized Next.js build
- 🔌 gRPC client for agent communication

## Tech Stack

- **Framework**: Next.js 14 (App Router)
- **Language**: TypeScript
- **Styling**: Tailwind CSS
- **UI Components**: shadcn/ui + Radix UI
- **gRPC**: @grpc/grpc-js
- **Markdown**: react-markdown + remark-gfm + rehype-highlight

## Development

```bash
# Install dependencies
npm install

# Run development server
npm run dev

# Build for production
npm run build

# Start production server
npm start
```

## Docker

The service is containerized using a multi-stage build for optimal image size and performance.

```bash
# Build
make build-ui

# Run
make up
```

Access the UI at http://localhost:5001
