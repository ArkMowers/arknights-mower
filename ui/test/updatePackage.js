import { BlobWriter, TextReader, ZipWriter } from '@zip.js/zip.js'

export async function zipPackage(paths, name = '任意改名 (1).bin') {
  const writer = new ZipWriter(new BlobWriter(), { useWebWorkers: false, level: 0 })
  for (const path of paths) await writer.add(path, new TextReader('fixture'))
  return new File([await writer.close()], name, { type: 'application/octet-stream' })
}
