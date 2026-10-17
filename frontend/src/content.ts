import type { Content, ContentKind } from "./types";

// Typed tool output determines placement. Never infer destinations from prose/keywords.
export const contentDefinitions = {
  description: { label: "Event description", destination: "details" },
  plain_language_summary: {
    label: "Plain-language summary",
    destination: "inclusion",
  },
  flyer_brief: { label: "Canva design instructions", destination: "design" },
  flyer_copy: { label: "Flyer text", destination: "design" },
  flyer_alt_text: { label: "Flyer accessible text", destination: "design" },
  event_document: { label: "Event document", destination: "documents" },
  invitation: { label: "Invitation", destination: "distribution" },
  change_notice: { label: "Change notice", destination: "distribution" },
} as const satisfies Record<
  ContentKind,
  { label: string; destination: string }
>;
export const destinations = [
  { id: "details", label: "Event details" },
  { id: "design", label: "Canva design" },
  { id: "inclusion", label: "Inclusion" },
  { id: "documents", label: "Documents" },
  { id: "distribution", label: "Distribution" },
] as const;
export type ContentDestination = (typeof destinations)[number]["id"];
export function normalizeContentKind(kind: unknown): ContentKind {
  // Member 3 supports legacy summary/document alongside the explicit asset kind names.
  if (kind === "summary") return "plain_language_summary";
  if (kind === "document") return "event_document";
  if (typeof kind !== "string" || !Object.hasOwn(contentDefinitions, kind))
    throw new Error(
      "Unsupported Go content kind. The event was not imported; a tool-schema update is required.",
    );
  return kind as ContentKind;
}
export function routeContent(
  items: Content[],
): Record<ContentDestination, Content[]> {
  const grouped: Record<ContentDestination, Content[]> = {
    details: [],
    design: [],
    inclusion: [],
    documents: [],
    distribution: [],
  };
  for (const item of items)
    grouped[contentDefinitions[item.kind].destination].push(item);
  return grouped;
}
