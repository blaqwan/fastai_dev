#AUTOGENERATED! DO NOT EDIT! File to edit: dev/30_text_core.ipynb (unless otherwise specified).

__all__ = ['ProcessPoolExecutor', 'parallel', 'parallel_gen', 'UNK', 'PAD', 'BOS', 'EOS', 'FLD', 'TK_REP', 'TK_WREP',
           'TK_UP', 'TK_MAJ', 'spec_add_spaces', 'rm_useless_spaces', 'replace_rep', 'replace_wrep', 'fix_html',
           'replace_all_caps', 'replace_maj', 'lowercase', 'replace_space', 'BaseTokenizer', 'SpacyTokenizer',
           'apply_rules', 'TokenizeBatch', 'tokenize1', 'parallel_tokenize', 'tokenize_folder', 'tokenize_df',
           'tokenize_csv', 'SentencePieceTokenizer']

from ..imports import *
from ..test import *
from ..core import *
from ..data.core import *
from ..data.external import *
from ..notebook.showdoc import show_doc

import concurrent.futures
from concurrent.futures import as_completed
from multiprocessing import Process, Queue
import spacy,html
from spacy.symbols import ORTH

class ProcessPoolExecutor(concurrent.futures.ProcessPoolExecutor):
    def __init__(self, max_workers=None, mp_context=None, initializer=None, initargs=()):
        self.no_workers = max_workers==0
        if self.no_workers: max_workers=1
        super().__init__(max_workers, mp_context, initializer=initializer, initargs=initializer)

    def map(self, f, items):
        return [f(o) for o in items] if self.no_workers else super().map(f, items)

def parallel(func, items, n_workers=defaults.cpus):
    "Applies `func` in parallel to `items`, using `n_workers`"
    with ProcessPoolExecutor(max_workers=n_workers) as ex:
        return [x for x in progress_bar(ex.map(func,items), total=len(items), leave=False)]

def parallel_gen(cls, items, n_workers=defaults.cpus, as_gen=False, **kwargs):
    "Instantiate `cls` in `n_workers` procs & call each on a subset of `items` in parallel."
    queue = Queue()
    batches = np.array_split(items, n_workers)
    idx = np.cumsum(0 + L(batches).mapped(len))
    def _f(batch, start_idx):
        f = cls(**kwargs)
        for i,b in enumerate(f(batch)): queue.put((start_idx+i,b))
    processes = [Process(target=_f, args=o) for o in zip(batches,idx)]
    for p in processes: p.start()
    res = (queue.get() for _ in progress_bar(items, leave=False))
    try: return res if as_gen else [o[1] for o in sorted(res)]
    finally:
        for p in processes: p.join()

#special tokens
UNK, PAD, BOS, EOS, FLD, TK_REP, TK_WREP, TK_UP, TK_MAJ = "xxunk xxpad xxbos xxeos xxfld xxrep xxwrep xxup xxmaj".split()

_re_spec = re.compile(r'([/#\\])')

def spec_add_spaces(t):
    "Add spaces around / and #"
    return _re_spec.sub(r' \1 ', t)

_re_space = re.compile(' {2,}')

def rm_useless_spaces(t):
    "Remove multiple spaces"
    return _re_space.sub(' ', t)

_re_rep = re.compile(r'(\S)(\1{2,})')

def replace_rep(t):
    "Replace repetitions at the character level: cccc -> TK_REP 4 c"
    def _replace_rep(m):
        c,cc = m.groups()
        return f' {TK_REP} {len(cc)+1} {c} '
    return _re_rep.sub(_replace_rep, t)

_re_wrep = re.compile(r'(?:\s|^)(\w+)\s+((?:\1\s+)+)\1(\s|\W|$)')

def replace_wrep(t):
    "Replace word repetitions: word word word word -> TK_WREP 4 word"
    def _replace_wrep(m):
        c,cc,e = m.groups()
        return f' {TK_WREP} {len(cc.split())+2} {c} {e}'
    return _re_wrep.sub(_replace_wrep, t)

def fix_html(x):
    "Various messy things we've seen in documents"
    x = x.replace('#39;', "'").replace('amp;', '&').replace('#146;', "'").replace('nbsp;', ' ').replace(
        '#36;', '$').replace('\\n', "\n").replace('quot;', "'").replace('<br />', "\n").replace(
        '\\"', '"').replace('<unk>',UNK).replace(' @.@ ','.').replace(' @-@ ','-').replace('...',' …')
    return html.unescape(x)

_re_all_caps = re.compile(r'(\s|^)([A-Z]+[^a-z\s]*)(?=(\s|$))')

def replace_all_caps(t):
    "Replace tokens in ALL CAPS by their lower version and add `TK_UP` before."
    def _replace_all_caps(m):
        tok = f'{TK_UP} ' if len(m.groups()[1]) > 1 else ''
        return f"{m.groups()[0]}{tok}{m.groups()[1].lower()}"
    return _re_all_caps.sub(_replace_all_caps, t)

_re_maj = re.compile(r'(\s|^)([A-Z][^A-Z\s]*)(?=(\s|$))')

def replace_maj(t):
    "Replace tokens in ALL CAPS by their lower version and add `TK_UP` before."
    def _replace_maj(m):
        tok = f'{TK_MAJ} ' if len(m.groups()[1]) > 1 else ''
        return f"{m.groups()[0]}{tok}{m.groups()[1].lower()}"
    return _re_maj.sub(_replace_maj, t)

def lowercase(t, add_bos=True, add_eos=False):
    "Converts `t` to lowercase"
    return (f'{BOS} ' if add_bos else '') + t.lower().strip() + (f' {EOS}' if add_eos else '')

def replace_space(t):
    "Replace embedded spaces in a token with unicode line char to allow for split/join"
    return t.replace(' ', '▁')

defaults.text_spec_tok = [UNK, PAD, BOS, EOS, FLD, TK_REP, TK_WREP, TK_UP, TK_MAJ]
defaults.text_proc_rules = [fix_html, replace_rep, replace_wrep, spec_add_spaces, rm_useless_spaces,
                            replace_all_caps, replace_maj, lowercase]
defaults.text_postproc_rules = [replace_space]

class BaseTokenizer():
    "Basic tokenizer that just splits on spaces"
    def __init__(self, split_char=' ', **kwargs): self.split_char=split_char
    def pipe(self, items): return (t.split(self.split_char) for t in items)

class SpacyTokenizer():
    "Spacy tokenizer for `lang`"
    def __init__(self, lang='en', special_toks=None, batch_size=5000):
        special_toks = ifnone(special_toks, defaults.text_spec_tok)
        self.nlp = spacy.blank(lang, disable=["parser", "tagger", "ner"])
        for w in special_toks: self.nlp.tokenizer.add_special_case(w, [{ORTH: w}])
        self.batch_size=batch_size

    def pipe(self, items):
        for doc in self.nlp.pipe(items, batch_size=self.batch_size):
            yield [d.text for d in doc]

def apply_rules(items, rules):
    "Returns a generator that apply `rules`  to `items`"
    return map(compose(*rules), items)

class TokenizeBatch:
    "A wrapper around `tok_func` to apply `rules` and tokenize in parallel"
    def __init__(self, tok_func=SpacyTokenizer, rules=None, post_rules=None, **tok_kwargs ):
        self.rules = L(ifnone(rules, defaults.text_proc_rules))
        self.post_f = compose(*L(ifnone(post_rules, defaults.text_postproc_rules)))
        self.tok = tok_func(**tok_kwargs)

    def __call__(self, batch):
        for o in self.tok.pipe(apply_rules(batch, self.rules)): yield L(o).mapped(self.post_f)

def tokenize1(text, tok_func=SpacyTokenizer, rules=None, post_rules=None, **tok_kwargs):
    "Tokenize one `text` with an instance of `tok_func` and some `rules`"
    return next(iter(TokenizeBatch(tok_func, rules, post_rules, **tok_kwargs)([text])))

def parallel_tokenize(items, tok_func, rules, as_gen=False, n_workers=defaults.cpus, **tok_kwargs):
    "Calls a potential setup on `tok_func` before launching `TokenizeBatch` in parallel"
    if hasattr(tok_func, 'setup'): tok_kwargs = tok_func(**tok_kwargs).setup(items, rules)
    return parallel_gen(TokenizeBatch, items, as_gen=as_gen, tok_func=tok_func,
                        rules=rules, n_workers=n_workers, **tok_kwargs)

@patch
def read(self:Path):
    "Read the content of `fname`"
    with self.open() as f: return f.read()

@patch
def write(self:Path, txt):
    "Write `txt` to `self`, creating directories as needed"
    self.parent.mkdir(parents=True,exist_ok=True)
    with self.open('w') as f: f.write(txt)

def tokenize_folder(path, extensions=None, include=None, output_dir=None, n_workers=defaults.cpus,
                    rules=None, tok_func=SpacyTokenizer, **tok_kwargs):
    "Tokenize text files in `path` in parallel using `n_workers`"
    path,extensions = Path(path),ifnone(extensions, ['.txt'])
    fnames = get_files(path, extensions=extensions, recurse=True, include=include)
    output_dir = Path(ifnone(output_dir, path.parent/f'{path.name}_tok'))
    rules = Path.read + L(ifnone(rules, defaults.text_proc_rules.copy()))

    counter = Counter()
    for i,tok in parallel_tokenize(fnames, tok_func, rules, as_gen=True, n_workers=n_workers, **tok_kwargs):
        out = output_dir/fnames[i].relative_to(path)
        out.write(' '.join(tok))
        out.with_suffix('.len').write(str(len(tok)))
        counter.update(tok)

    pickle.dump(counter, open(output_dir/'counter.pkl','wb'))

def _join_texts(df, mark_fields=False):
    "Join texts in row `idx` of `df`, marking each field with `FLD` if `mark_fields=True`"
    text_col = (f'{FLD} {1} ' if mark_fields else '' ) + df.iloc[:,0].astype(str)
    for i in range(1,len(df.columns)):
        text_col += (f' {FLD} {i+1} ' if mark_fields else ' ') + df.iloc[:,i].astype(str)
    return text_col.values

def tokenize_df(df, text_cols, n_workers=defaults.cpus, rules=None, mark_fields=None,
                tok_func=SpacyTokenizer, **tok_kwargs):
    "Tokenize texts in `df[text_cols]` in parallel using `n_workers`"
    text_cols = L(text_cols)
    mark_fields = ifnone(mark_fields, len(text_cols) > 1)
    rules = L(ifnone(rules, defaults.text_proc_rules.copy()))
    texts = _join_texts(df[text_cols], mark_fields=mark_fields)
    lengths,outputs,counter = [],[],Counter()

    for tok in parallel_tokenize(texts, tok_func, rules, n_workers=n_workers, **tok_kwargs):
        lengths.append(len(tok))
        outputs.append(' '.join(tok))
        counter.update(tok)

    other_cols = [c for c in df.columns if c not in text_cols]
    res = df[other_cols].copy()
    res['text'],res['text_lengths'] = outputs,lengths
    return res,counter

#TODO: test + rework
def tokenize_csv(fname, text_cols, outname=None, n_workers=4, rules=None, mark_fields=None,
                 tok_func=SpacyTokenizer, header='infer', chunksize=None, **tok_kwargs):
    "Tokenize texts in the `text_cols` of the csv `fname` in parallel using `n_workers`"
    df = pd.read_csv(fname, header=header, chunksize=chunksize)
    outname = Path(ifnone(outname, fname.parent/f'{fname.stem}_tok.csv'))
    kwargs = dict(n_workers=n_workers, pre_rules=pre_rules, post_rules=post_rules,
                  mark_fields=mark_fields, tok_func=tok_func, **tok_kwargs)
    if chunksize is None:
        out,cnt = tok_df(df, text_cols, **kwargs)
        out.to_csv(outname, header=header, index=False)
    else:
        cnt = Counter()
        for i,dfp in enumerate(df):
            out,c = tok_df(dfp, text_cols, **kwargs)
            out.to_csv(outname, header=header if i==0 else None, index=False, mode='w' if i==0 else 'a')
            cnt.update(c)
    pickle.dump(cnt, open(outname.parent/'counter.pkl', 'wb'))

class SentencePieceTokenizer():#TODO: pass the special tokens symbol to sp
    "Spacy tokenizer for `lang`"
    def __init__(self, lang='en', special_toks=None, sp_model=None, vocab_sz=None, max_vocab_sz=30000,
                 model_type='unigram', char_coverage=None, cache_dir='tmp'):
        try: from sentencepiece import SentencePieceTrainer,SentencePieceProcessor
        except ImportError:
            raise Exception('sentencepiece module is missing: run `pip install sentencepiece`')
        self.sp_model,self.cache_dir = sp_model,Path(cache_dir)
        self.vocab_sz,self.max_vocab_sz,self.model_type = vocab_sz,max_vocab_sz,model_type
        self.char_coverage = ifnone(char_coverage, 0.99999 if lang in eu_langs else 0.9998)
        self.special_toks = ifnone(special_toks, defaults.text_spec_tok)
        if sp_model is None: self.tok = None
        else:
            self.tok = SentencePieceProcessor()
            self.tok.Load(str(sp_model))
        os.makedirs(self.cache_dir, exist_ok=True)

    def _get_vocab_sz(self, raw_text_path):
        cnt = Counter()
        with open(raw_text_path, 'r') as f:
            for line in f.readlines():
                cnt.update(line.split())
                if len(cnt)//4 > self.max_vocab_sz: return self.max_vocab_sz
        res = len(cnt)//4
        while res%8 != 0: res+=1
        return res

    def train(self, raw_text_path):
        "Train a sentencepiece tokenizer on `texts` and save it in `path/tmp_dir`"
        from sentencepiece import SentencePieceTrainer
        vocab_sz = self._get_vocab_sz(raw_text_path) if self.vocab_sz is None else self.vocab_sz
        spec_tokens = ['\u2581'+s for s in self.special_toks]
        SentencePieceTrainer.Train(" ".join([
            f"--input={raw_text_path} --vocab_size={vocab_sz} --model_prefix={self.cache_dir/'spm'}",
            f"--character_coverage={self.char_coverage} --model_type={self.model_type}",
            f"--unk_id={len(spec_tokens)} --pad_id=-1 --bos_id=-1 --eos_id=-1",
            f"--user_defined_symbols={','.join(spec_tokens)}"]))
        raw_text_path.unlink()
        return self.cache_dir/'spm.model'

    def setup(self, items, rules):
        if self.tok is not None: return {'sp_model': self.sp_model}
        raw_text_path = self.cache_dir/'texts.out'
        with open(raw_text_path, 'w') as f:
            for t in progress_bar(apply_rules(items, rules), total=len(items), leave=False):
                f.write(f'{t}\n')
        return {'sp_model': self.train(raw_text_path)}

    def pipe(self, items):
        for t in items: yield self.tok.EncodeAsPieces(t)