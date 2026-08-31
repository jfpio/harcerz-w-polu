import { defineCollection, z } from 'astro:content';
import { docsLoader } from '@astrojs/starlight/loaders';
import { docsSchema } from '@astrojs/starlight/schema';

export const collections = {
  docs: defineCollection({
    loader: docsLoader(),
    schema: docsSchema({
      extend: z.object({
        number: z.number().int().min(1).max(117).optional(),
        section: z.string().optional(),
        order: z.number().int().nonnegative().optional(),
        printedPages: z.array(z.number().int().positive()).optional(),
        pdfPages: z.array(z.number().int().positive()).optional(),
        forOlderScouts: z.boolean().optional(),
        status: z.enum(['ocr-beta', 'verified']).optional(),
        sourceUrl: z.string().url().optional(),
      }),
    }),
  }),
};
