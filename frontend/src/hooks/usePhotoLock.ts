import { useQuery } from '@tanstack/react-query'
import { photoLockApi } from '@/api/endpoints'
import { keys } from '@/api/keys'

/**
 * Whether progress photos come blurred. The server decides; `version` goes into the photo
 * addresses so they load again the moment the state changes (the unlock runs out by
 * itself, so it is checked again every minute while open).
 */
export function usePhotoLock() {
  const lock = useQuery({
    queryKey: keys.photoLock,
    queryFn: ({ signal }) => photoLockApi.get({ signal }),
    refetchInterval: (query) => (query.state.data?.unlocked ? 60_000 : false),
  })
  const data = lock.data
  const version = !data?.enabled ? '' : data.unlocked ? `open-${data.unlocked_until}` : 'veiled'
  return { lock: data, version, hidden: Boolean(data?.enabled && !data.unlocked) }
}
