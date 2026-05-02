import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
import test from 'node:test';

const require = createRequire(import.meta.url);
const {
  buildLaunchPlan,
  buildRequestDefaults,
} = require('../dist/main/shared/commandBuilder.js');

test('buildLaunchPlan maps server, deployment, and redaction fields', () => {
  const plan = buildLaunchPlan(
    'C:\\Program Files\\TurboLauncher\\llama-server.exe',
    'C:\\models\\example.gguf',
    {
      Host: '0.0.0.0',
      Port: 8080,
      ApiKey: 'super-secret-key',
      Webui: false,
      Metrics: true,
      MultiModel: true,
      ModelsDir: 'D:\\models',
      ModelsMax: 12,
      ModelsAutoload: false,
      ContBatching: true,
      Threads: 24,
      BatchSize: 1024,
      UBatchSize: 256,
      Parallel: 3,
      LogVerbosity: 'info',
    },
    {
      Alias: 'test-alias',
      CtxSize: 131072,
      GpuLayers: 42,
      NcpuMoe: 28,
      CacheTypeK: 'q4_0',
      CacheTypeV: 'q8_0',
      FlashAttn: 'on',
      SplitMode: 'row',
      TensorSplit: '1,2',
      MainGpu: 1,
      Device: 'cuda:0',
      Mlock: true,
      NoMmap: true,
      Jinja: false,
      ChatTemplate: 'chatml',
      MaxTokens: 128,
      Temp: 0.7,
      TopP: 0.9,
      TopK: 40,
      MinP: 0.05,
      TypicalP: 0.8,
      RepeatPenalty: 1.1,
      RepeatLastN: 32,
      PresencePenalty: 0.25,
      FreqPenalty: 0.1,
      StopSequences: 'END\nSTOP',
      Seed: 99,
    },
  );

  assert.equal(plan.deployment.mode, 'multi-model-repository');
  assert.equal(plan.deployment.modelsDir, 'D:\\models');
  assert.equal(plan.deployment.alias, 'test-alias');

  assert.equal(plan.args.host, '0.0.0.0');
  assert.equal(plan.args.port, 8080);
  assert.equal(plan.args['api-key'], 'super-secret-key');
  assert.equal(plan.args.metrics, true);
  assert.equal(plan.args['no-webui'], true);
  assert.equal(plan.args['cont-batching'], true);
  assert.equal(plan.args['models-dir'], 'D:\\models');
  assert.equal(plan.args['models-max'], 12);
  assert.equal(plan.args['no-models-autoload'], true);

  assert.equal(plan.args.model, undefined);
  assert.equal(plan.args.alias, 'test-alias');
  assert.equal(plan.args['ctx-size'], 131072);
  assert.equal(plan.args['n-gpu-layers'], 42);
  assert.equal(plan.args['n-cpu-moe'], 28);
  assert.equal(plan.args['cache-type-k'], 'q4_0');
  assert.equal(plan.args['cache-type-v'], 'q8_0');
  assert.equal(plan.args['flash-attn'], 'on');
  assert.equal(plan.args['split-mode'], 'row');
  assert.equal(plan.args['tensor-split'], '1,2');
  assert.equal(plan.args['main-gpu'], 1);
  assert.equal(plan.args.device, 'cuda:0');
  assert.equal(plan.args.mlock, true);
  assert.equal(plan.args['no-mmap'], true);
  assert.equal(plan.args['no-jinja'], true);
  assert.equal(plan.args['chat-template'], 'chatml');

  assert.equal(plan.args.temp, 0.7);
  assert.equal(plan.args['top-p'], 0.9);
  assert.equal(plan.args['top-k'], 40);
  assert.equal(plan.args['min-p'], 0.05);
  assert.equal(plan.args['typical-p'], 0.8);
  assert.equal(plan.args['repeat-penalty'], 1.1);
  assert.equal(plan.args['repeat-last-n'], 32);
  assert.equal(plan.args['presence-penalty'], 0.25);
  assert.equal(plan.args['frequency-penalty'], 0.1);
  assert.equal(plan.args.seed, 99);

  assert.ok(!('app-name' in plan.args));
  assert.ok(!('app-version' in plan.args));
  assert.ok(!('productName' in plan.args));

  assert.equal(plan.redactedArgs['api-key'], '***');
  assert.ok(!plan.redactedCommandText.includes('super-secret-key'));
  assert.ok(plan.redactedCommandText.includes('--api-key ***'));
});

test('buildLaunchPlan maps single-model load args', () => {
  const plan = buildLaunchPlan(
    'llama-server.exe',
    'C:\\models\\single.gguf',
    {
      Host: '127.0.0.1',
      Port: 1234,
      ApiKey: '',
      Webui: true,
      Metrics: false,
      MultiModel: false,
      ModelsDir: '',
      ModelsMax: 4,
      ModelsAutoload: true,
      ContBatching: false,
      Threads: 16,
      BatchSize: 512,
      UBatchSize: 512,
      Parallel: 1,
      LogVerbosity: '',
    },
    {
      Alias: 'single-model-alias',
      FlashAttn: 'off',
      Jinja: true,
      CtxSize: 8192,
      GpuLayers: 8,
      CacheTypeK: 'q4_0',
      CacheTypeV: 'q8_0',
    },
  );

  assert.equal(plan.deployment.mode, 'single-model-process');
  assert.equal(plan.deployment.modelPath, 'C:\\models\\single.gguf');
  assert.equal(plan.deployment.alias, 'single-model-alias');

  assert.equal(plan.args.model, 'C:\\models\\single.gguf');
  assert.equal(plan.args.alias, 'single-model-alias');
  assert.equal(plan.args['ctx-size'], 8192);
  assert.equal(plan.args['n-gpu-layers'], 8);
  assert.equal(plan.args['cache-type-k'], 'q4_0');
  assert.equal(plan.args['cache-type-v'], 'q8_0');
  assert.equal(plan.args['flash-attn'], 'off');
  assert.equal(plan.args.jinja, true);
  assert.equal(plan.args['no-jinja'], undefined);
});

test('buildRequestDefaults maps stop sequences, max tokens, and sampling fields', () => {
  const defaults = buildRequestDefaults({
    StopSequences: 'END\n  STOP  \n\nFINAL',
    MaxTokens: 256,
    Temp: 0.2,
    TopP: 0.88,
    TopK: 50,
    MinP: 0.03,
    TypicalP: 0.91,
    RepeatPenalty: 1.07,
    PresencePenalty: 0.2,
    FreqPenalty: 0.05,
  });

  assert.equal(defaults.temperature, 0.2);
  assert.equal(defaults.top_p, 0.88);
  assert.equal(defaults.top_k, 50);
  assert.equal(defaults.min_p, 0.03);
  assert.equal(defaults.typical_p, 0.91);
  assert.equal(defaults.repeat_penalty, 1.07);
  assert.equal(defaults.presence_penalty, 0.2);
  assert.equal(defaults.frequency_penalty, 0.05);
  assert.equal(defaults.max_tokens, 256);
  assert.deepEqual(defaults.stop, ['END', 'STOP', 'FINAL']);
});
