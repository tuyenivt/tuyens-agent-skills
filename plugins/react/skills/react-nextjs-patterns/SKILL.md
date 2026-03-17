---
name: react-nextjs-patterns
description: Next.js App Router patterns - Server Components, Server Actions, ISR, middleware, dynamic routes, image optimization, and metadata API for Next.js 15+.
metadata:
  category: frontend
  tags: [nextjs, server-components, server-actions, isr, metadata, image-optimization]
user-invocable: false
---

# Next.js App Router Patterns

> Load `Use skill: stack-detect` first to determine the project stack.

## When to Use

- Building features with Next.js App Router
- Deciding between Server Components and Client Components
- Implementing Server Actions for form handling and mutations
- Configuring caching, ISR, or dynamic rendering
- Optimizing images, metadata, and SEO

## Rules

- Server Components are the default - only add `"use client"` when the component needs hooks, event handlers, or browser APIs
- Server Actions must validate all input - they are public HTTP endpoints
- Never import server-only code (database clients, secrets) in Client Components
- Use the `next/image` component for all images - never use raw `<img>` tags
- Metadata must be defined via the Metadata API (generateMetadata) - not manual `<head>` tags
- Prefer static rendering by default; opt into dynamic rendering only when needed (cookies, headers, searchParams)
- Cache aggressively, invalidate deliberately - use `revalidatePath` and `revalidateTag`

## Patterns

### Server Components Data Fetching

```tsx
// Server Component - fetch data directly (no hooks needed)
async function ProductList({ category }: { category: string }) {
  const products = await db.product.findMany({ where: { category } });
  return (
    <ul>
      {products.map((p) => (
        <ProductCard key={p.id} product={p} />
      ))}
    </ul>
  );
}
```

**Fetch with caching and revalidation:**

```tsx
async function getProducts(category: string) {
  const res = await fetch(`${API_URL}/products?category=${category}`, {
    next: { revalidate: 3600, tags: ["products"] }, // ISR: revalidate every hour
  });
  if (!res.ok) throw new Error("Failed to fetch products");
  return res.json() as Promise<Product[]>;
}
```

### Server Actions

**Form mutation with Server Action:**

```tsx
// app/actions.ts
"use server";

import { revalidatePath } from "next/cache";
import { z } from "zod";

const CreatePostSchema = z.object({
  title: z.string().min(1).max(200),
  content: z.string().min(1),
});

export async function createPost(formData: FormData) {
  const parsed = CreatePostSchema.safeParse({
    title: formData.get("title"),
    content: formData.get("content"),
  });

  if (!parsed.success) {
    return { error: parsed.error.flatten().fieldErrors };
  }

  await db.post.create({ data: parsed.data });
  revalidatePath("/posts");
}
```

**Using Server Actions in Client Components:**

```tsx
"use client";

import { createPost } from "./actions";

function CreatePostForm() {
  const [state, formAction, isPending] = useActionState(createPost, null);

  return (
    <form action={formAction}>
      <input name="title" required />
      {state?.error?.title && <p role="alert">{state.error.title}</p>}
      <textarea name="content" required />
      <button disabled={isPending}>
        {isPending ? "Creating..." : "Create Post"}
      </button>
    </form>
  );
}
```

### Rendering Strategies

| Strategy      | When to Use                                  | Configuration                          |
| ------------- | -------------------------------------------- | -------------------------------------- |
| Static (SSG)  | Content that rarely changes                  | Default (no dynamic APIs)              |
| ISR           | Content that changes periodically            | `revalidate: N` (seconds)              |
| Dynamic (SSR) | Personalized content, real-time data         | Use cookies(), headers(), searchParams |
| Client-side   | Highly interactive, user-specific after load | `"use client"` + TanStack Query        |

**Force dynamic rendering:**

```tsx
// Only when you need per-request data
export const dynamic = "force-dynamic";

export default async function DashboardPage() {
  const session = await getSession(); // needs cookies()
  const data = await getDashboardData(session.userId);
  return <Dashboard data={data} />;
}
```

### Image Optimization

```tsx
import Image from "next/image";

// Static import (auto-sized, optimized at build)
import heroImg from "@/public/hero.jpg";

function Hero() {
  return (
    <Image
      src={heroImg}
      alt="Hero banner"
      priority // LCP image - preload
      placeholder="blur" // blur placeholder from static import
    />
  );
}

// Remote image (must configure domains in next.config)
function Avatar({ user }: { user: User }) {
  return (
    <Image
      src={user.avatarUrl}
      alt={`${user.name}'s avatar`}
      width={48}
      height={48}
      className="rounded-full"
    />
  );
}
```

### Metadata API

```tsx
// Static metadata
export const metadata: Metadata = {
  title: "My App",
  description: "App description",
};

// Dynamic metadata
export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const post = await getPost(slug);
  return {
    title: post.title,
    description: post.excerpt,
    openGraph: {
      title: post.title,
      description: post.excerpt,
      images: [post.coverImage],
    },
  };
}
```

### Streaming with Suspense

```tsx
export default function DashboardPage() {
  return (
    <div>
      <h1>Dashboard</h1>
      {/* Show immediately */}
      <WelcomeBanner />

      {/* Stream in when ready */}
      <Suspense fallback={<ChartSkeleton />}>
        <RevenueChart /> {/* async Server Component */}
      </Suspense>

      <Suspense fallback={<TableSkeleton />}>
        <RecentOrders /> {/* async Server Component */}
      </Suspense>
    </div>
  );
}
```

### Route Handlers (API Routes)

```tsx
// app/api/users/route.ts
import { NextRequest, NextResponse } from "next/server";

export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const page = parseInt(searchParams.get("page") || "1");
  const users = await getUsers({ page, limit: 20 });
  return NextResponse.json(users);
}

export async function POST(request: NextRequest) {
  const body = await request.json();
  const parsed = CreateUserSchema.safeParse(body);
  if (!parsed.success) {
    return NextResponse.json(
      { errors: parsed.error.flatten() },
      { status: 400 },
    );
  }
  const user = await createUser(parsed.data);
  return NextResponse.json(user, { status: 201 });
}
```

### Server-Only Code Protection

```tsx
// lib/db.ts
import "server-only"; // throws build error if imported in Client Component

import { PrismaClient } from "@prisma/client";
export const db = new PrismaClient();
```

## Output Format

Consuming workflow skills depend on this structure.

```
## Next.js Architecture

**Next.js version:** {detected version}
**Rendering strategy:** {Static | ISR | Dynamic | Mixed}

### Route Configuration

| Route              | Rendering  | Revalidation | Data Source      | Auth       |
| ------------------ | ---------- | ------------ | ---------------- | ---------- |
| /                  | Static     | -            | None             | Public     |
| /products          | ISR        | 3600s        | DB via Server    | Public     |
| /dashboard         | Dynamic    | -            | API + cookies    | Protected  |

### Server Actions

| Action           | Validation    | Revalidation           |
| ---------------- | ------------- | ---------------------- |
| {actionName}     | {Zod schema}  | {revalidatePath/Tag}   |

### Recommendations

- {recommendation with rationale}

### Issues Found

- [Severity: High | Medium | Low] {description}
  - Problem: {what is wrong}
  - Fix: {concrete correction}
```

## Avoid

- Using `"use client"` on components that don't need interactivity (ships unnecessary JS)
- Importing database clients or secrets in Client Components (exposes server code)
- Using raw `<img>` tags instead of `next/image` (no optimization, no lazy loading, CLS)
- Manual `<head>` manipulation instead of Metadata API (inconsistent, SSR issues)
- Server Actions without input validation (they are public HTTP endpoints)
- Using `force-dynamic` on pages that could be statically rendered (unnecessary server load)
- Fetching data in Client Components when a Server Component could fetch it directly
- Using `router.push` for simple link navigation instead of `<Link>` (no prefetching)
