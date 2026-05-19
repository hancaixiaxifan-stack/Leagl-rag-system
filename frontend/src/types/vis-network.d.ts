declare module "vis-network/standalone" {
  export interface Node {
    id: string | number;
    label?: string;
    shape?: string;
    size?: number;
    color?: string | {
      background?: string;
      border?: string;
      highlight?: { background?: string; border?: string };
    };
    font?: {
      size?: number;
      color?: string;
      face?: string;
      multi?: string;
    };
    borderWidth?: number;
    borderWidthSelected?: number;
    shadow?: { enabled?: boolean; color?: string; size?: number };
    margin?: number;
    x?: number;
    y?: number;
    fixed?: boolean;
    category?: string;
    data?: unknown;
    [key: string]: unknown;
  }

  export interface Edge {
    id?: string | number;
    from: string | number;
    to: string | number;
    label?: string;
    color?: string | { color?: string; opacity?: number };
    width?: number;
    dashes?: boolean | number[];
    arrows?: { to?: { enabled?: boolean; scaleFactor?: number } };
    smooth?: { type?: string; roundness?: number };
    lineStyle?: { color?: string; width?: number; type?: string; curveness?: number; opacity?: number };
    [key: string]: unknown;
  }

  export interface Options {
    layout?: { improvedLayout?: boolean };
    physics?: {
      enabled?: boolean;
      solver?: string;
      forceAtlas2Based?: {
        gravitationalConstant?: number;
        centralGravity?: number;
        springLength?: number;
        springConstant?: number;
        damping?: number;
        avoidOverlap?: number;
      };
      stabilization?: {
        enabled?: boolean;
        iterations?: number;
        updateInterval?: number;
      };
      adaptiveTimestep?: boolean;
    };
    interaction?: {
      hover?: boolean;
      tooltipDelay?: number;
      zoomView?: boolean;
      dragView?: boolean;
      navigationButtons?: boolean;
    };
    nodes?: {
      borderWidth?: number;
      borderWidthSelected?: number;
      chosen?: boolean | { node?: (values: unknown, id: string, selected: boolean, hovering: boolean) => void };
    };
    edges?: {
      color?: { inherit?: string };
      smooth?: { enabled?: boolean; type?: string };
    };
  }

  export interface Data {
    nodes: Node[] | DataSet<Node>;
    edges: Edge[] | DataSet<Edge>;
  }

  export class DataSet<T> {
    constructor(data?: T[]);
    add(data: T | T[]): (string | number)[];
    update(data: T | T[]): (string | number)[];
    remove(ids: string | number | (string | number)[]): (string | number)[];
    get(ids?: string | number | (string | number)[]): T[];
    getIds(): (string | number)[];
    length: number;
    on(event: string, callback: (event: unknown, properties: unknown, senderId: string | number) => void): void;
    off(event: string, callback?: (event: unknown, properties: unknown, senderId: string | number) => void): void;
  }

  export type NetworkEvents =
    | "click"
    | "doubleClick"
    | "hoverNode"
    | "blurNode"
    | "zoom"
    | "dragStart"
    | "dragEnd"
    | "stabilizationIterationsDone"
    | "stabilized";

  export interface ClickEvent {
    nodes: (string | number)[];
    edges: (string | number)[];
    event: unknown;
    pointer: { DOM: { x: number; y: number }; canvas: { x: number; y: number } };
    data?: unknown;
    dataType?: string;
  }

  export class Network {
    constructor(container: HTMLElement, data: Data, options?: Options);
    destroy(): void;
    setData(data: Data): void;
    setOptions(options: Options): void;
    fit(options?: { animation?: boolean | { duration?: number; easingFunction?: string } }): void;
    focus(nodeId: string | number, options?: { animation?: boolean | { duration?: number; easingFunction?: string } }): void;
    selectNodes(nodeIds: (string | number)[], highlightEdges?: boolean): void;
    getSelectedNodes(): (string | number)[];
    getPosition(nodeId: string | number): { x: number; y: number };
    on(event: NetworkEvents, callback: (params: ClickEvent) => void): void;
    off(event: NetworkEvents, callback?: (params: ClickEvent) => void): void;
    once(event: NetworkEvents, callback: (params: ClickEvent) => void): void;
    canvasToDOM(position: { x: number; y: number }): { x: number; y: number };
    DOMtoCanvas(position: { x: number; y: number }): { x: number; y: number };
    getScale(): number;
    setSize(width: string, height: string): void;
    redraw(): void;
  }
}
