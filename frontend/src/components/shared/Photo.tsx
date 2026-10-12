import { useState, type CSSProperties } from 'react'
import { ImageOff } from 'lucide-react'
import { mediaUrl } from '@/api/client'
import { cn } from '@/lib/utils'

/**
 * A private photo served by the backend to its owner. Lazy, with a quiet placeholder when
 * the photo storage is unavailable.
 */
export function Photo({
  id,
  alt,
  size = 'preview',
  className,
  style,
  eager = false,
  fit = 'cover',
  version = '',
}: {
  id: number
  alt: string
  size?: 'preview' | 'original'
  className?: string
  style?: CSSProperties
  eager?: boolean
  fit?: 'cover' | 'contain'
  /** See mediaUrl: a new value loads the photo again. */
  version?: string
}) {
  const [failed, setFailed] = useState(false)
  return (
    <span className={cn('photo-frame block', className)} style={style}>
      {failed ? (
        <span className="photo-fallback" role="img" aria-label={`${alt}: не загрузилось`}>
          <ImageOff className="size-5" aria-hidden="true" />
        </span>
      ) : (
        <img
          src={mediaUrl(id, size, version)}
          alt={alt}
          loading={eager ? 'eager' : 'lazy'}
          decoding="async"
          draggable={false}
          onError={() => setFailed(true)}
          style={{ objectFit: fit }}
        />
      )}
    </span>
  )
}
