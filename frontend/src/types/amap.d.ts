declare namespace AMap {
  class Map {
    constructor(container: string | HTMLElement, opts?: MapOptions)
    setCenter(lnglat: LngLat): void
    add(control: any): void
    plugin(name: string | string[], callback: Function): void
    setFitView( markers?: Marker[] ): void
  }

  interface MapOptions {
    zoom?: number
    center?: LngLat
    viewMode?: string
    mapStyle?: string
  }

  class LngLat {
    constructor(lng: number, lat: number)
  }

  class Marker {
    constructor(opts?: MarkerOptions)
    setPosition(lnglat: LngLat): void
    getPosition(): LngLat
    setMap(map: Map): void
    setTitle(title: string): void
    on(type: string, handler: Function): void
  }

  interface MarkerOptions {
    position?: LngLat
    title?: string
    icon?: Icon
    offset?: Pixel
    draggable?: boolean
    content?: string | HTMLElement
  }

  class Icon {
    constructor(opts?: IconOptions)
  }

  interface IconOptions {
    size?: Pixel
    image?: string
    imageSize?: Pixel
  }

  class Pixel {
    constructor(x: number, y: number)
  }

  class InfoWindow {
    constructor(opts?: InfoWindowOptions)
    open(map: Map, pos: LngLat): void
    close(): void
    setContent(content: string | HTMLElement): void
  }

  interface InfoWindowOptions {
    content?: string | HTMLElement
    offset?: Pixel
    closeWhenClickMap?: boolean
  }

  class Scale {
    constructor()
  }

  class ToolBar {
    constructor()
  }
}

interface Window {
  AMap: typeof AMap
  _AMapSecurityConfig: {
    securityJsCode: string
  }
}
