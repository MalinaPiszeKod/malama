import fs from 'node:fs/promises';
import path from 'node:path';

export class JsonStore {
  async read<T>(filePath: string, fallback: T): Promise<T> {
    try {
      const text = await fs.readFile(filePath, 'utf8');
      return JSON.parse(text) as T;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code === 'ENOENT') return fallback;
      try {
        await fs.copyFile(filePath, `${filePath}.bak`);
      } catch {
        // Preserve best-effort fallback behavior if the original file cannot be copied.
      }
      return fallback;
    }
  }

  async write<T>(filePath: string, value: T): Promise<void> {
    await fs.mkdir(path.dirname(filePath), { recursive: true });
    const tempPath = `${filePath}.${process.pid}.${Date.now()}.tmp`;
    await fs.writeFile(tempPath, `${JSON.stringify(value, null, 2)}\n`, 'utf8');
    await fs.rename(tempPath, filePath);
  }
}
