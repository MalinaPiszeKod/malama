import fs from 'node:fs/promises';

export type GgufScalar = string | number | boolean | bigint;
export type GgufValue = GgufScalar | GgufScalar[];

export interface GgufMetadata {
  version: number;
  tensorCount: bigint;
  metadataCount: bigint;
  values: Record<string, GgufValue>;
  quant?: string;
}

const GGUF_MAGIC = 'GGUF';
const MAX_STRING_BYTES = 1024 * 1024;
const MAX_ARRAY_ELEMENTS_TO_KEEP = 128;
const READ_BUFFER_BYTES = 4 * 1024 * 1024;

enum GgufValueType {
  Uint8 = 0,
  Int8 = 1,
  Uint16 = 2,
  Int16 = 3,
  Uint32 = 4,
  Int32 = 5,
  Float32 = 6,
  Bool = 7,
  String = 8,
  Array = 9,
  Uint64 = 10,
  Int64 = 11,
  Float64 = 12,
}

const FILE_TYPE_QUANTS: Record<number, string> = {
  0: 'F32',
  1: 'F16',
  2: 'Q4_0',
  3: 'Q4_1',
  7: 'Q8_0',
  8: 'Q5_0',
  9: 'Q5_1',
  10: 'Q2_K',
  11: 'Q3_K_S',
  12: 'Q3_K_M',
  13: 'Q3_K_L',
  14: 'Q4_K_S',
  15: 'Q4_K_M',
  16: 'Q5_K_S',
  17: 'Q5_K_M',
  18: 'Q6_K',
  19: 'IQ2_XXS',
  20: 'IQ2_XS',
  21: 'Q2_K_S',
  22: 'IQ3_XS',
  23: 'IQ3_XXS',
  24: 'IQ1_S',
  25: 'IQ4_NL',
  26: 'IQ3_S',
  27: 'IQ3_M',
  28: 'IQ2_S',
  29: 'IQ2_M',
  30: 'IQ4_XS',
  31: 'IQ1_M',
  32: 'BF16',
  33: 'Q4_0_4_4',
  34: 'Q4_0_4_8',
  35: 'Q4_0_8_8',
  36: 'TQ1_0',
  37: 'TQ2_0',
  38: 'MXFP4',
};

class GgufReader {
  private offset = 0;
  private buffer = Buffer.alloc(0);
  private bufferStart = 0;
  private bufferEnd = 0;

  constructor(private readonly handle: fs.FileHandle) {}

  async readBytes(length: number): Promise<Buffer> {
    if (!Number.isSafeInteger(length) || length < 0) throw new Error(`Invalid GGUF read length: ${length}`);
    if (length === 0) return Buffer.alloc(0);

    if (length <= READ_BUFFER_BYTES) {
      await this.ensureBuffered(length);
      const start = this.offset - this.bufferStart;
      const end = start + length;
      const bytes = Buffer.from(this.buffer.subarray(start, end));
      this.offset += length;
      return bytes;
    }

    const buffer = Buffer.alloc(length);
    const { bytesRead } = await this.handle.read(buffer, 0, length, this.offset);
    if (bytesRead !== length) throw new Error('Unexpected end of GGUF file');
    this.offset += length;
    this.clearBuffer();
    return buffer;
  }

  skip(length: number): void {
    if (!Number.isSafeInteger(length) || length < 0) throw new Error(`Invalid GGUF skip length: ${length}`);
    this.offset += length;
    if (this.offset < this.bufferStart || this.offset > this.bufferEnd) this.clearBuffer();
  }

  async uint32(): Promise<number> {
    return (await this.readBytes(4)).readUInt32LE(0);
  }

  async uint64(): Promise<bigint> {
    return (await this.readBytes(8)).readBigUInt64LE(0);
  }

  async ggufString(keep = true): Promise<string> {
    const length = Number(await this.uint64());
    if (!Number.isSafeInteger(length)) throw new Error('GGUF string is too large');
    if (!keep) {
      this.skip(length);
      return '';
    }
    if (length > MAX_STRING_BYTES) {
      this.skip(length);
      return `[string ${length} bytes]`;
    }
    return (await this.readBytes(length)).toString('utf8');
  }

  private async ensureBuffered(length: number): Promise<void> {
    if (this.offset >= this.bufferStart && this.offset + length <= this.bufferEnd) return;

    const size = Math.max(READ_BUFFER_BYTES, length);
    const buffer = Buffer.alloc(size);
    const { bytesRead } = await this.handle.read(buffer, 0, size, this.offset);
    if (bytesRead < length) throw new Error('Unexpected end of GGUF file');
    this.buffer = bytesRead === size ? buffer : buffer.subarray(0, bytesRead);
    this.bufferStart = this.offset;
    this.bufferEnd = this.offset + bytesRead;
  }

  private clearBuffer(): void {
    this.buffer = Buffer.alloc(0);
    this.bufferStart = this.offset;
    this.bufferEnd = this.offset;
  }
}

export async function readGgufMetadata(filePath: string): Promise<GgufMetadata | null> {
  let handle: fs.FileHandle | undefined;
  try {
    handle = await fs.open(filePath, 'r');
    const reader = new GgufReader(handle);
    const magic = (await reader.readBytes(4)).toString('ascii');
    if (magic !== GGUF_MAGIC) return null;

    const version = await reader.uint32();
    const tensorCount = await reader.uint64();
    const metadataCount = await reader.uint64();
    if (metadataCount > BigInt(Number.MAX_SAFE_INTEGER)) return null;

    const values: Record<string, GgufValue> = {};
    for (let index = 0; index < Number(metadataCount); index += 1) {
      const key = await reader.ggufString();
      const type = await reader.uint32();
      const keep = shouldKeepValue(key, type);
      const value = await readValue(reader, type, keep);
      if (value !== undefined) values[key] = value;
    }

    const fileType = numberFromValue(values['general.file_type']);
    return {
      version,
      tensorCount,
      metadataCount,
      values,
      ...(fileType !== undefined && FILE_TYPE_QUANTS[fileType] ? { quant: FILE_TYPE_QUANTS[fileType] } : {}),
    };
  } catch {
    return null;
  } finally {
    await handle?.close();
  }
}

async function readValue(reader: GgufReader, type: number, keep: boolean): Promise<GgufValue | undefined> {
  switch (type) {
    case GgufValueType.Uint8:
      return (await reader.readBytes(1)).readUInt8(0);
    case GgufValueType.Int8:
      return (await reader.readBytes(1)).readInt8(0);
    case GgufValueType.Uint16:
      return (await reader.readBytes(2)).readUInt16LE(0);
    case GgufValueType.Int16:
      return (await reader.readBytes(2)).readInt16LE(0);
    case GgufValueType.Uint32:
      return (await reader.readBytes(4)).readUInt32LE(0);
    case GgufValueType.Int32:
      return (await reader.readBytes(4)).readInt32LE(0);
    case GgufValueType.Float32:
      return roundNumber((await reader.readBytes(4)).readFloatLE(0));
    case GgufValueType.Bool:
      return (await reader.readBytes(1)).readUInt8(0) !== 0;
    case GgufValueType.String:
      return reader.ggufString(keep);
    case GgufValueType.Array:
      return readArray(reader, keep);
    case GgufValueType.Uint64:
      return await reader.uint64();
    case GgufValueType.Int64:
      return (await reader.readBytes(8)).readBigInt64LE(0);
    case GgufValueType.Float64:
      return roundNumber((await reader.readBytes(8)).readDoubleLE(0));
    default:
      throw new Error(`Unsupported GGUF value type: ${type}`);
  }
}

async function readArray(reader: GgufReader, keep: boolean): Promise<GgufValue | undefined> {
  const itemType = await reader.uint32();
  const length = Number(await reader.uint64());
  if (!Number.isSafeInteger(length)) throw new Error('GGUF array is too large');

  const shouldKeep = keep && length <= MAX_ARRAY_ELEMENTS_TO_KEEP;
  if (!shouldKeep) {
    const itemSize = scalarByteSize(itemType);
    if (itemSize !== undefined) {
      reader.skip(length * itemSize);
      return `[array ${typeName(itemType)} x ${length}]`;
    }
    if (itemType !== GgufValueType.String) throw new Error(`Unsupported GGUF array item type: ${itemType}`);
  }

  const items: GgufScalar[] = [];
  for (let index = 0; index < length; index += 1) {
    const item = await readValue(reader, itemType, shouldKeep);
    if (shouldKeep && isScalar(item)) items.push(item);
  }

  return shouldKeep ? items : `[array ${typeName(itemType)} x ${length}]`;
}

function shouldKeepValue(key: string, type: number): boolean {
  if (type !== GgufValueType.Array) return true;
  return /(^|\.)(tags?|languages?|license|licenses)$/i.test(key);
}

function isScalar(value: GgufValue | undefined): value is GgufScalar {
  return ['string', 'number', 'boolean', 'bigint'].includes(typeof value);
}

function numberFromValue(value: GgufValue | undefined): number | undefined {
  if (typeof value === 'number') return value;
  if (typeof value === 'bigint' && value <= BigInt(Number.MAX_SAFE_INTEGER)) return Number(value);
  return undefined;
}

function roundNumber(value: number): number {
  return Number(value.toFixed(6));
}

function scalarByteSize(type: number): number | undefined {
  switch (type) {
    case GgufValueType.Uint8:
    case GgufValueType.Int8:
    case GgufValueType.Bool:
      return 1;
    case GgufValueType.Uint16:
    case GgufValueType.Int16:
      return 2;
    case GgufValueType.Uint32:
    case GgufValueType.Int32:
    case GgufValueType.Float32:
      return 4;
    case GgufValueType.Uint64:
    case GgufValueType.Int64:
    case GgufValueType.Float64:
      return 8;
    default:
      return undefined;
  }
}

function typeName(type: number): string {
  return GgufValueType[type] ?? `type ${type}`;
}
