import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as mediaLibraryApi from "./api";

export const mediaLibraryKeys = {
  assets: ["media-assets"] as const,
};

export function useMediaAssets() {
  return useQuery({
    queryKey: mediaLibraryKeys.assets,
    queryFn: mediaLibraryApi.fetchMediaAssets,
  });
}

export function useDeleteMediaAsset() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => mediaLibraryApi.deleteMediaAsset(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: mediaLibraryKeys.assets });
    },
  });
}

export function useUploadMedia() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ instanceId, file }: { instanceId: string; file: File }) =>
      mediaLibraryApi.uploadMedia(instanceId, file),
    onSuccess: () => {
      // Upload has a backend side effect of inserting a `media_assets` row -
      // refetch rather than reaching for the response body ourselves.
      void queryClient.invalidateQueries({ queryKey: mediaLibraryKeys.assets });
    },
  });
}
