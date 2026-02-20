/**
 * Lightweight syntax highlighting for code blocks.
 *
 * Supports: JavaScript, TypeScript, Python, Bash, JSON, Rust, Go, CSS, HTML
 * Uses regex-based tokenization for simplicity without external dependencies.
 */

import { escapeHtml } from './dom';

// Token types
type TokenType =
  | 'keyword'
  | 'string'
  | 'number'
  | 'comment'
  | 'function'
  | 'operator'
  | 'punctuation'
  | 'type'
  | 'variable'
  | 'property';

// CSS classes for each token type
const TOKEN_CLASSES: Record<TokenType, string> = {
  keyword: 'hl-keyword',
  string: 'hl-string',
  number: 'hl-number',
  comment: 'hl-comment',
  function: 'hl-function',
  operator: 'hl-operator',
  punctuation: 'hl-punctuation',
  type: 'hl-type',
  variable: 'hl-variable',
  property: 'hl-property',
};

// Language definitions
const LANGUAGES: Record<string, {
  keywords: string[];
  types?: string[];
  singleLineComment?: string;
  multiLineComment?: [string, string];
  strings?: string[];
}> = {
  javascript: {
    keywords: ['const', 'let', 'var', 'function', 'return', 'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'break', 'continue', 'try', 'catch', 'finally', 'throw', 'new', 'class', 'extends', 'import', 'export', 'default', 'from', 'async', 'await', 'yield', 'this', 'super', 'typeof', 'instanceof', 'in', 'of', 'true', 'false', 'null', 'undefined', 'void', 'delete'],
    types: ['string', 'number', 'boolean', 'object', 'symbol', 'bigint', 'any', 'unknown', 'never', 'void', 'Promise', 'Array', 'Object', 'Map', 'Set', 'Date', 'RegExp', 'Error'],
    singleLineComment: '//',
    multiLineComment: ['/*', '*/'],
    strings: ['"', "'", '`'],
  },
  typescript: {
    keywords: ['const', 'let', 'var', 'function', 'return', 'if', 'else', 'for', 'while', 'do', 'switch', 'case', 'break', 'continue', 'try', 'catch', 'finally', 'throw', 'new', 'class', 'extends', 'implements', 'import', 'export', 'default', 'from', 'async', 'await', 'yield', 'this', 'super', 'typeof', 'instanceof', 'in', 'of', 'true', 'false', 'null', 'undefined', 'void', 'delete', 'interface', 'type', 'enum', 'namespace', 'module', 'declare', 'abstract', 'private', 'protected', 'public', 'readonly', 'static', 'as', 'is', 'keyof', 'infer'],
    types: ['string', 'number', 'boolean', 'object', 'symbol', 'bigint', 'any', 'unknown', 'never', 'void', 'Promise', 'Array', 'Object', 'Map', 'Set', 'Date', 'RegExp', 'Error', 'Partial', 'Required', 'Readonly', 'Record', 'Pick', 'Omit', 'Exclude', 'Extract', 'ReturnType', 'Parameters'],
    singleLineComment: '//',
    multiLineComment: ['/*', '*/'],
    strings: ['"', "'", '`'],
  },
  python: {
    keywords: ['def', 'class', 'return', 'if', 'elif', 'else', 'for', 'while', 'break', 'continue', 'try', 'except', 'finally', 'raise', 'with', 'as', 'import', 'from', 'lambda', 'yield', 'global', 'nonlocal', 'pass', 'assert', 'del', 'True', 'False', 'None', 'and', 'or', 'not', 'in', 'is', 'async', 'await', 'match', 'case'],
    types: ['str', 'int', 'float', 'bool', 'list', 'dict', 'tuple', 'set', 'frozenset', 'bytes', 'bytearray', 'memoryview', 'range', 'type', 'object', 'Exception', 'Optional', 'Union', 'List', 'Dict', 'Tuple', 'Set', 'Any', 'Callable', 'TypeVar', 'Generic'],
    singleLineComment: '#',
    multiLineComment: ['"""', '"""'],
    strings: ['"', "'"],
  },
  bash: {
    keywords: ['if', 'then', 'else', 'elif', 'fi', 'for', 'while', 'do', 'done', 'case', 'esac', 'in', 'function', 'return', 'local', 'export', 'readonly', 'declare', 'typeset', 'source', 'alias', 'unalias', 'set', 'unset', 'shift', 'exit', 'break', 'continue', 'trap', 'eval', 'exec', 'true', 'false'],
    singleLineComment: '#',
    strings: ['"', "'"],
  },
  json: {
    keywords: ['true', 'false', 'null'],
    strings: ['"'],
  },
  rust: {
    keywords: ['fn', 'let', 'mut', 'const', 'static', 'struct', 'enum', 'impl', 'trait', 'type', 'where', 'for', 'loop', 'while', 'if', 'else', 'match', 'return', 'break', 'continue', 'use', 'mod', 'pub', 'crate', 'self', 'super', 'as', 'in', 'ref', 'move', 'async', 'await', 'dyn', 'unsafe', 'extern', 'true', 'false'],
    types: ['i8', 'i16', 'i32', 'i64', 'i128', 'isize', 'u8', 'u16', 'u32', 'u64', 'u128', 'usize', 'f32', 'f64', 'bool', 'char', 'str', 'String', 'Vec', 'Box', 'Option', 'Result', 'Some', 'None', 'Ok', 'Err', 'Self'],
    singleLineComment: '//',
    multiLineComment: ['/*', '*/'],
    strings: ['"'],
  },
  go: {
    keywords: ['func', 'return', 'if', 'else', 'for', 'range', 'switch', 'case', 'default', 'break', 'continue', 'goto', 'fallthrough', 'defer', 'go', 'select', 'chan', 'package', 'import', 'type', 'struct', 'interface', 'map', 'const', 'var', 'true', 'false', 'nil', 'iota'],
    types: ['int', 'int8', 'int16', 'int32', 'int64', 'uint', 'uint8', 'uint16', 'uint32', 'uint64', 'uintptr', 'float32', 'float64', 'complex64', 'complex128', 'bool', 'byte', 'rune', 'string', 'error'],
    singleLineComment: '//',
    multiLineComment: ['/*', '*/'],
    strings: ['"', '`'],
  },
  css: {
    keywords: ['important', 'inherit', 'initial', 'unset', 'auto', 'none'],
    singleLineComment: undefined,
    multiLineComment: ['/*', '*/'],
    strings: ['"', "'"],
  },
  html: {
    keywords: [],
    multiLineComment: ['<!--', '-->'],
    strings: ['"', "'"],
  },
};

// Alias mappings
const LANGUAGE_ALIASES: Record<string, string> = {
  js: 'javascript',
  ts: 'typescript',
  py: 'python',
  sh: 'bash',
  shell: 'bash',
  zsh: 'bash',
  rs: 'rust',
  golang: 'go',
};

// escapeHtml imported from './dom'

// Simple tokenizer
function highlightCode(code: string, language: string): string {
  const lang = LANGUAGE_ALIASES[language.toLowerCase()] || language.toLowerCase();
  const langDef = LANGUAGES[lang];

  if (!langDef) {
    // Fallback: just escape HTML
    return escapeHtml(code);
  }

  let result = '';
  let i = 0;

  while (i < code.length) {
    // Check for multi-line comment
    if (langDef.multiLineComment) {
      const [start, end] = langDef.multiLineComment;
      if (code.slice(i, i + start.length) === start) {
        const endIndex = code.indexOf(end, i + start.length);
        const commentEnd = endIndex === -1 ? code.length : endIndex + end.length;
        result += `<span class="${TOKEN_CLASSES.comment}">${escapeHtml(code.slice(i, commentEnd))}</span>`;
        i = commentEnd;
        continue;
      }
    }

    // Check for single-line comment
    if (langDef.singleLineComment) {
      if (code.slice(i, i + langDef.singleLineComment.length) === langDef.singleLineComment) {
        const lineEnd = code.indexOf('\n', i);
        const commentEnd = lineEnd === -1 ? code.length : lineEnd;
        result += `<span class="${TOKEN_CLASSES.comment}">${escapeHtml(code.slice(i, commentEnd))}</span>`;
        i = commentEnd;
        continue;
      }
    }

    // Check for strings
    if (langDef.strings) {
      for (const quote of langDef.strings) {
        if (code.slice(i, i + quote.length) === quote) {
          let j = i + quote.length;
          while (j < code.length) {
            if (code[j] === '\\' && j + 1 < code.length) {
              j += 2; // Skip escaped character
            } else if (code.slice(j, j + quote.length) === quote) {
              j += quote.length;
              break;
            } else if (quote !== '`' && code[j] === '\n') {
              break; // End of line for single-line strings
            } else {
              j++;
            }
          }
          result += `<span class="${TOKEN_CLASSES.string}">${escapeHtml(code.slice(i, j))}</span>`;
          i = j;
          continue;
        }
      }
    }

    // Check for numbers
    const numberMatch = code.slice(i).match(/^(\d+\.?\d*([eE][+-]?\d+)?|0x[0-9a-fA-F]+|0b[01]+|0o[0-7]+)/);
    if (numberMatch && (i === 0 || !/\w/.test(code[i - 1]))) {
      result += `<span class="${TOKEN_CLASSES.number}">${escapeHtml(numberMatch[0])}</span>`;
      i += numberMatch[0].length;
      continue;
    }

    // Check for identifiers (keywords, types, functions)
    const identMatch = code.slice(i).match(/^[a-zA-Z_$][a-zA-Z0-9_$]*/);
    if (identMatch) {
      const ident = identMatch[0];

      // Check if it's followed by ( - likely a function
      const afterIdent = code.slice(i + ident.length).match(/^\s*\(/);

      if (langDef.keywords.includes(ident)) {
        result += `<span class="${TOKEN_CLASSES.keyword}">${escapeHtml(ident)}</span>`;
      } else if (langDef.types?.includes(ident)) {
        result += `<span class="${TOKEN_CLASSES.type}">${escapeHtml(ident)}</span>`;
      } else if (afterIdent) {
        result += `<span class="${TOKEN_CLASSES.function}">${escapeHtml(ident)}</span>`;
      } else {
        result += escapeHtml(ident);
      }
      i += ident.length;
      continue;
    }

    // Check for operators
    const opMatch = code.slice(i).match(/^(===|!==|==|!=|<=|>=|&&|\|\||<<|>>|>>>|\+\+|--|=>|\+=|-=|\*=|\/=|%=|&=|\|=|\^=|<<=|>>=|>>>=|\?\?|\.\.\.|\?\.|[+\-*/%&|^~!<>=?:])/);
    if (opMatch) {
      result += `<span class="${TOKEN_CLASSES.operator}">${escapeHtml(opMatch[0])}</span>`;
      i += opMatch[0].length;
      continue;
    }

    // Check for punctuation
    const punctMatch = code.slice(i).match(/^[{}[\]();,.]/);
    if (punctMatch) {
      result += `<span class="${TOKEN_CLASSES.punctuation}">${escapeHtml(punctMatch[0])}</span>`;
      i += 1;
      continue;
    }

    // Default: just add the character
    result += escapeHtml(code[i]);
    i++;
  }

  return result;
}

/**
 * Highlight a code block and return HTML.
 */
export function highlight(code: string, language?: string): string {
  const lang = language || 'text';
  return highlightCode(code, lang);
}

/**
 * Detect language from filename extension.
 */
export function detectLanguage(filename: string): string {
  const ext = filename.split('.').pop()?.toLowerCase() || '';
  const extensionMap: Record<string, string> = {
    js: 'javascript',
    jsx: 'javascript',
    ts: 'typescript',
    tsx: 'typescript',
    py: 'python',
    sh: 'bash',
    bash: 'bash',
    zsh: 'bash',
    json: 'json',
    rs: 'rust',
    go: 'go',
    css: 'css',
    scss: 'css',
    less: 'css',
    html: 'html',
    htm: 'html',
    xml: 'html',
    md: 'markdown',
    yaml: 'yaml',
    yml: 'yaml',
    toml: 'toml',
    sql: 'sql',
  };
  return extensionMap[ext] || 'text';
}

/**
 * Get CSS styles for syntax highlighting.
 * Call this once to inject the styles into the document.
 */
export function getSyntaxHighlightCSS(): string {
  return `
    .hl-keyword { color: #c586c0; font-weight: 500; }
    .hl-string { color: #ce9178; }
    .hl-number { color: #b5cea8; }
    .hl-comment { color: #6a9955; font-style: italic; }
    .hl-function { color: #dcdcaa; }
    .hl-operator { color: #d4d4d4; }
    .hl-punctuation { color: #d4d4d4; }
    .hl-type { color: #4ec9b0; }
    .hl-variable { color: #9cdcfe; }
    .hl-property { color: #9cdcfe; }
  `;
}

/**
 * Inject syntax highlighting styles into the document.
 */
export function injectSyntaxHighlightStyles(): void {
  if (document.querySelector('style[data-syntax-highlight]')) {
    return; // Already injected
  }
  const style = document.createElement('style');
  style.setAttribute('data-syntax-highlight', 'true');
  style.textContent = getSyntaxHighlightCSS();
  document.head.appendChild(style);
}
