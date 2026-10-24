/** Phone photos are 4–12 MB and sometimes HEIC: before upload they become a JPEG of at
 * most 2048 px on the long side (plenty for the assistant), so several fit in one request.
 * A file the browser cannot decode goes as it is and the server decides. */
export async function shrinkPhoto(file: File, side = 2048): Promise<Blob> {
  try {
    const bitmap = await createImageBitmap(file)
    const scale = Math.min(1, side / Math.max(bitmap.width, bitmap.height))
    const canvas = document.createElement('canvas')
    canvas.width = Math.round(bitmap.width * scale)
    canvas.height = Math.round(bitmap.height * scale)
    canvas.getContext('2d')!.drawImage(bitmap, 0, 0, canvas.width, canvas.height)
    bitmap.close()
    const blob = await new Promise<Blob | null>((resolve) =>
      canvas.toBlob(resolve, 'image/jpeg', 0.86),
    )
    if (!blob) return file
    // HEIC and the like always go as JPEG; a small JPEG may stay as it was.
    if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type)) return blob
    return blob.size < file.size ? blob : file
  } catch {
    return file
  }
}
