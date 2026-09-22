import { useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { MapContainer, Marker, TileLayer, useMapEvents } from "react-leaflet";
import { Input } from "@fusion-flow/ui";

// Vite doesn't resolve Leaflet's default marker image URLs correctly out
// of the box (the CSS references relative paths that break under a
// bundler) - point them at the same CDN Leaflet's own docs recommend
// instead of bundling the image assets ourselves.
const markerIcon = L.icon({
  iconUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon.png",
  iconRetinaUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-icon-2x.png",
  shadowUrl: "https://unpkg.com/leaflet@1.9.4/dist/images/marker-shadow.png",
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  shadowSize: [41, 41],
});

export interface SelectedLocation {
  latitude: number;
  longitude: number;
  name: string | null;
  address: string | null;
}

interface LocationPickerProps {
  value: SelectedLocation | null;
  onChange: (location: SelectedLocation) => void;
}

function ClickToPlaceMarker({ onPick }: { onPick: (lat: number, lng: number) => void }) {
  useMapEvents({
    click(event) {
      onPick(event.latlng.lat, event.latlng.lng);
    },
  });
  return null;
}

const DEFAULT_CENTER: [number, number] = [20, 0];

/**
 * Click-to-drop-a-pin location picker, for the "Location" attachment on a
 * WhatsApp Broadcast Campaign (WhatsApp's `send_location_message` action
 * - Instagram has no location-sending capability at all, so this
 * component is only ever rendered for a WhatsApp-selected campaign).
 * Uses OpenStreetMap tiles via Leaflet - no API key/billing account
 * needed, unlike Google Maps.
 */
export function LocationPicker({ value, onChange }: LocationPickerProps) {
  const [name, setName] = useState(value?.name ?? "");
  const [address, setAddress] = useState(value?.address ?? "");

  function handlePick(lat: number, lng: number) {
    onChange({ latitude: lat, longitude: lng, name: name.trim() || null, address: address.trim() || null });
  }

  function handleNameChange(next: string) {
    setName(next);
    if (value) onChange({ ...value, name: next.trim() || null });
  }

  function handleAddressChange(next: string) {
    setAddress(next);
    if (value) onChange({ ...value, address: next.trim() || null });
  }

  const center: [number, number] = value ? [value.latitude, value.longitude] : DEFAULT_CENTER;

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs text-muted-foreground">Click the map to drop a pin at the location to send.</p>
      <div className="h-64 overflow-hidden rounded-md border border-border">
        <MapContainer center={center} zoom={value ? 13 : 2} scrollWheelZoom className="h-full w-full">
          <TileLayer
            attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
            url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
          />
          <ClickToPlaceMarker onPick={handlePick} />
          {value && <Marker position={[value.latitude, value.longitude]} icon={markerIcon} />}
        </MapContainer>
      </div>
      {value ? (
        <p className="text-xs text-muted-foreground">
          {value.latitude.toFixed(5)}, {value.longitude.toFixed(5)}
        </p>
      ) : (
        <p className="text-xs text-muted-foreground">No location picked yet.</p>
      )}
      <div className="grid gap-2 sm:grid-cols-2">
        <Input
          placeholder="Location name (optional)"
          value={name}
          onChange={(event) => handleNameChange(event.target.value)}
        />
        <Input
          placeholder="Address (optional)"
          value={address}
          onChange={(event) => handleAddressChange(event.target.value)}
        />
      </div>
    </div>
  );
}
