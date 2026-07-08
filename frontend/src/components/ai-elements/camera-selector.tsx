"use client";

import { useControllableState } from "@radix-ui/react-use-controllable-state";
import { ChevronsUpDownIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { Button } from "@/components/ui/button";
import {
  Command,
  CommandEmpty,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import {
  Popover,
  PopoverContent,
  PopoverTrigger,
} from "@/components/ui/popover";
import { cn } from "@/lib/utils";

interface CameraSelectorContextType {
  data: MediaDeviceInfo[];
  value: string | undefined;
  onValueChange?: (value: string) => void;
  open: boolean;
  onOpenChange?: (open: boolean) => void;
  width: number;
  setWidth?: (width: number) => void;
}

const CameraSelectorContext = createContext<CameraSelectorContextType>({
  data: [],
  onOpenChange: undefined,
  onValueChange: undefined,
  open: false,
  setWidth: undefined,
  value: undefined,
  width: 200,
});

/**
 * Enumerate every camera the device exposes (built-in front/rear, USB webcams,
 * continuity/iPhone cameras, capture cards, ...). Labels only populate after
 * camera permission is granted, so we lazily request it when the picker opens.
 */
export const useVideoDevices = () => {
  const [devices, setDevices] = useState<MediaDeviceInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [hasPermission, setHasPermission] = useState(false);

  const loadWithoutPermission = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const list = await navigator.mediaDevices.enumerateDevices();
      setDevices(list.filter((device) => device.kind === "videoinput"));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to get cameras");
    } finally {
      setLoading(false);
    }
  }, []);

  const loadDevices = useCallback(async () => {
    if (loading) {
      return;
    }
    try {
      setLoading(true);
      setError(null);
      const temp = await navigator.mediaDevices.getUserMedia({ video: true });
      for (const track of temp.getTracks()) {
        track.stop();
      }
      const list = await navigator.mediaDevices.enumerateDevices();
      setDevices(list.filter((device) => device.kind === "videoinput"));
      setHasPermission(true);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Failed to get cameras");
    } finally {
      setLoading(false);
    }
  }, [loading]);

  useEffect(() => {
    loadWithoutPermission();
  }, [loadWithoutPermission]);

  useEffect(() => {
    const onChange = () => {
      if (hasPermission) {
        loadDevices();
      } else {
        loadWithoutPermission();
      }
    };
    navigator.mediaDevices.addEventListener("devicechange", onChange);
    return () => navigator.mediaDevices.removeEventListener("devicechange", onChange);
  }, [hasPermission, loadDevices, loadWithoutPermission]);

  return { devices, error, hasPermission, loadDevices, loading };
};

export type CameraSelectorProps = ComponentProps<typeof Popover> & {
  defaultValue?: string;
  value?: string | undefined;
  onValueChange?: (value: string | undefined) => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
};

export const CameraSelector = ({
  defaultValue,
  value: controlledValue,
  onValueChange: controlledOnValueChange,
  defaultOpen = false,
  open: controlledOpen,
  onOpenChange: controlledOnOpenChange,
  ...props
}: CameraSelectorProps) => {
  const [value, onValueChange] = useControllableState<string | undefined>({
    defaultProp: defaultValue,
    onChange: controlledOnValueChange,
    prop: controlledValue,
  });
  const [open, onOpenChange] = useControllableState({
    defaultProp: defaultOpen,
    onChange: controlledOnOpenChange,
    prop: controlledOpen,
  });
  const [width, setWidth] = useState(200);
  const { devices, loading, hasPermission, loadDevices } = useVideoDevices();

  useEffect(() => {
    if (open && !hasPermission && !loading) {
      loadDevices();
    }
  }, [open, hasPermission, loading, loadDevices]);

  const contextValue = useMemo(
    () => ({
      data: devices,
      onOpenChange,
      onValueChange,
      open,
      setWidth,
      value,
      width,
    }),
    [devices, onOpenChange, onValueChange, open, setWidth, value, width]
  );

  return (
    <CameraSelectorContext.Provider value={contextValue}>
      <Popover {...props} onOpenChange={onOpenChange} open={open} />
    </CameraSelectorContext.Provider>
  );
};

export type CameraSelectorTriggerProps = ComponentProps<typeof Button>;

export const CameraSelectorTrigger = ({
  children,
  ...props
}: CameraSelectorTriggerProps) => {
  const { setWidth } = useContext(CameraSelectorContext);
  const ref = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const newWidth = (entry.target as HTMLElement).offsetWidth;
        if (newWidth) {
          setWidth?.(newWidth);
        }
      }
    });
    if (ref.current) {
      observer.observe(ref.current);
    }
    return () => observer.disconnect();
  }, [setWidth]);

  return (
    <PopoverTrigger asChild>
      <Button variant="outline" {...props} ref={ref}>
        {children}
        <ChevronsUpDownIcon className="shrink-0 text-muted-foreground" size={16} />
      </Button>
    </PopoverTrigger>
  );
};

export type CameraSelectorContentProps = ComponentProps<typeof Command> & {
  popoverOptions?: ComponentProps<typeof PopoverContent>;
};

export const CameraSelectorContent = ({
  className,
  popoverOptions,
  ...props
}: CameraSelectorContentProps) => {
  const { width, onValueChange, value } = useContext(CameraSelectorContext);

  return (
    <PopoverContent className={cn("p-0", className)} style={{ width }} {...popoverOptions}>
      <Command onValueChange={onValueChange} value={value} {...props} />
    </PopoverContent>
  );
};

export type CameraSelectorInputProps = ComponentProps<typeof CommandInput>;

export const CameraSelectorInput = ({ ...props }: CameraSelectorInputProps) => (
  <CommandInput placeholder="Search cameras..." {...props} />
);

export type CameraSelectorListProps = Omit<
  ComponentProps<typeof CommandList>,
  "children"
> & {
  children: (devices: MediaDeviceInfo[]) => ReactNode;
};

export const CameraSelectorList = ({
  children,
  ...props
}: CameraSelectorListProps) => {
  const { data } = useContext(CameraSelectorContext);
  return <CommandList {...props}>{children(data)}</CommandList>;
};

export type CameraSelectorEmptyProps = ComponentProps<typeof CommandEmpty>;

export const CameraSelectorEmpty = ({
  children = "No camera found.",
  ...props
}: CameraSelectorEmptyProps) => <CommandEmpty {...props}>{children}</CommandEmpty>;

export type CameraSelectorItemProps = ComponentProps<typeof CommandItem>;

export const CameraSelectorItem = (props: CameraSelectorItemProps) => {
  const { onValueChange, onOpenChange } = useContext(CameraSelectorContext);

  const handleSelect = useCallback(
    (currentValue: string) => {
      onValueChange?.(currentValue);
      onOpenChange?.(false);
    },
    [onValueChange, onOpenChange]
  );

  return <CommandItem onSelect={handleSelect} {...props} />;
};

/** Human label for a camera, with a graceful fallback before permission grant. */
export const cameraLabel = (device: MediaDeviceInfo, index: number): string => {
  if (device.label) {
    return device.label;
  }
  return `Camera ${index + 1}`;
};
