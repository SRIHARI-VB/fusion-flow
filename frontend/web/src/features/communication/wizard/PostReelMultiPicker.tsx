import { useMemo, useState } from "react";
import { useInfiniteQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { Badge, Button, Input } from "@fusion-flow/ui";
import { fetchInstagramMediaPage, type InstagramMedia } from "../instagram/media-api";

interface PostReelMultiPickerProps {
  instanceId: string | undefined;
  /** Selected media ids - empty means "every post/reel" (account-wide). */
  value: string[];
  onChange: (ids: string[]) => void;
}

/**
 * Multi-select post/reel picker for Comment Automation/Comment
 * Moderation's "scope to specific posts/reels" option. An account can
 * have hundreds of posts and reels, so unlike a small fixed list this
 * pages through Meta's own cursor one batch at a time ("Load more"
 * rather than everything up front), and search only filters what's
 * already been loaded - there's no server-side text search on Instagram's
 * `/media` edge to build a real remote search against.
 *
 * Shared by `InstagramAutomationWizardPage.tsx` (Comment Automation) and
 * `InstagramCommentModerationWizardPage.tsx` (Comment Moderation) - both
 * scope to the same `media_ids: string[]` shape (`[]` = every post/reel).
 */
export function PostReelMultiPicker({ instanceId, value, onChange }: PostReelMultiPickerProps) {
  const [search, setSearch] = useState("");

  const { data, isLoading, isFetchingNextPage, hasNextPage, fetchNextPage } = useInfiniteQuery({
    queryKey: ["instagram-media-page", instanceId],
    queryFn: ({ pageParam }: { pageParam: string | null }) =>
      fetchInstagramMediaPage(instanceId as string, { after: pageParam, limit: 25 }),
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    enabled: Boolean(instanceId),
  });

  const loadedItems: InstagramMedia[] = useMemo(
    () => (data?.pages ?? []).flatMap((page) => page.items),
    [data],
  );

  const filteredItems = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return loadedItems;
    return loadedItems.filter(
      (item) => (item.caption ?? "").toLowerCase().includes(query) || item.id.includes(query),
    );
  }, [loadedItems, search]);

  const selectedItems = useMemo(
    () => loadedItems.filter((item) => value.includes(item.id)),
    [loadedItems, value],
  );

  function toggle(id: string) {
    onChange(value.includes(id) ? value.filter((existing) => existing !== id) : [...value, id]);
  }

  function clearAll() {
    onChange([]);
  }

  return (
    <div className="flex flex-col gap-2">
      <button
        type="button"
        onClick={clearAll}
        className={`flex items-center justify-between rounded-md border p-2 text-left text-sm transition-colors ${
          value.length === 0 ? "border-accent bg-accent-soft" : "border-border hover:bg-muted"
        }`}
      >
        <span className="font-medium">All posts/reels</span>
        <span className="text-xs text-muted-foreground">Account-wide (default)</span>
      </button>

      {value.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {selectedItems.map((item) => (
            <Badge key={item.id} variant="secondary" className="max-w-[10rem] truncate">
              {item.caption ? item.caption.slice(0, 24) : item.id}
            </Badge>
          ))}
          {value.length > selectedItems.length && (
            <Badge variant="outline">+{value.length - selectedItems.length} not yet loaded</Badge>
          )}
        </div>
      )}

      <Input
        placeholder="Search loaded posts/reels by caption…"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />

      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading posts/reels…</p>
      ) : filteredItems.length === 0 ? (
        <p className="text-xs text-muted-foreground">
          {loadedItems.length === 0 ? "No posts/reels found." : "No loaded posts/reels match that search."}
        </p>
      ) : (
        <div className="grid max-h-72 grid-cols-4 gap-2 overflow-y-auto rounded-md border border-border p-2">
          {filteredItems.map((item) => {
            const selected = value.includes(item.id);
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => toggle(item.id)}
                title={item.caption ?? item.id}
                className={`relative overflow-hidden rounded-md border ${
                  selected ? "border-accent ring-2 ring-accent" : "border-border hover:border-accent"
                }`}
              >
                {item.thumbnail_url || item.media_url ? (
                  <img
                    src={item.thumbnail_url ?? item.media_url ?? ""}
                    alt={item.caption ?? ""}
                    className="h-20 w-full object-cover"
                  />
                ) : (
                  <div className="flex h-20 w-full items-center justify-center bg-muted text-[10px] text-muted-foreground">
                    {item.media_type}
                  </div>
                )}
                {selected && (
                  <span className="absolute right-1 top-1 flex h-4 w-4 items-center justify-center rounded-full bg-accent text-[10px] text-white">
                    ✓
                  </span>
                )}
              </button>
            );
          })}
        </div>
      )}

      {hasNextPage && !search && (
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void fetchNextPage()}
          disabled={isFetchingNextPage}
          className="w-fit"
        >
          {isFetchingNextPage ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : null}
          {isFetchingNextPage ? "Loading…" : "Load more"}
        </Button>
      )}
      {search && (
        <p className="text-xs text-muted-foreground">
          Search only filters posts/reels already loaded above - clear it to load more first.
        </p>
      )}
    </div>
  );
}
