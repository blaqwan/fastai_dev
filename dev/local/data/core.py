#AUTOGENERATED! DO NOT EDIT! File to edit: dev/05_data_core.ipynb (unless otherwise specified).

__all__ = ['TfmdDL', 'DataBunch', 'FilteredBase', 'TfmdList', 'decode_at', 'show_at', 'DataSource', 'test_set',
           'test_dl']

#Cell
from ..torch_basics import *
from ..test import *
from ..transform import *
from .load import *
from ..notebook.showdoc import *

#Cell
_dl_tfms = ('after_item','before_batch','after_batch')

#Cell
@delegates()
class TfmdDL(DataLoader):
    "Transformed `DataLoader`"
    def __init__(self, dataset, bs=16, shuffle=False, num_workers=None, **kwargs):
        if num_workers is None: num_workers = min(16, defaults.cpus)
        for nm in _dl_tfms:
            kwargs[nm] = Pipeline(kwargs.get(nm,None), as_item=(nm=='before_batch'))
            kwargs[nm].setup(self)
        super().__init__(dataset, bs=bs, shuffle=shuffle, num_workers=num_workers, **kwargs)

    def _one_pass(self):
        its = self.after_batch(self.do_batch([self.do_item(0)]))
        self._device = find_device(its)
        self._retain_dl = partial(retain_types, typs=mapped(type,its))

    def _retain_dl(self,b):
        self._one_pass()
        # we just replaced ourselves, so this is *not* recursive! :)
        return self._retain_dl(b)

    def before_iter(self):
        super().before_iter()
        split_idx = getattr(self.dataset, 'split_idx', None)
        for nm in _dl_tfms:
            f = getattr(self,nm)
            if isinstance(f,Pipeline): f.split_idx=split_idx

    def decode(self, b): return self.before_batch.decode(self.after_batch.decode(self._retain_dl(b)))
    def decode_batch(self, b, max_n=10, ds_decode=True): return self._decode_batch(self.decode(b), max_n, ds_decode)

    def _decode_batch(self, b, max_n=10, ds_decode=True):
        f = self.after_item.decode
        if ds_decode: f = compose(f, getattr(self.dataset,'decode',noop))
        return L(batch_to_samples(b, max_n=max_n)).map(f)

    def show_batch(self, b=None, max_n=10, ctxs=None, **kwargs):
        "Show `b` (defaults to `one_batch`), a list of lists of pipeline outputs (i.e. output of a `DataLoader`)"
        if b is None: b = self.one_batch()
        b = self.decode(b)
        if hasattr(b, 'show'): return b.show(max_n=max_n, **kwargs)
        if ctxs is None:
            if hasattr(b[0], 'get_ctxs'): ctxs = b[0].get_ctxs(max_n=max_n, **kwargs)
            else: ctxs = [None] * len(b[0] if is_iter(b[0]) else b)
        db = self._decode_batch(b, max_n, False)
        ctxs = [self.dataset.show(o, ctx=ctx, **kwargs) for o,ctx in zip(db, ctxs)]
        if hasattr(b[0], 'display'): b[0].display(ctxs)

    @property
    def device(self):
        if not hasattr(self, '_device'): _ = self._one_pass()
        return self._device

    @property
    def n_inp(self):
        if hasattr(self.dataset, 'n_inp'): return self.dataset.n_inp
        its = self.after_batch(self.do_batch([self.do_item(0)]))
        return 1 if not isinstance(its, (list,tuple)) or len(its)==1 else len(its)-1

#Cell
@docs
class DataBunch(GetAttr):
    "Basic wrapper around several `DataLoader`s."
    _xtra='one_batch show_batch dataset device n_inp'.split()
    _default='train_dl'

    def __init__(self, *dls): self.dls = dls
    def __getitem__(self, i): return self.dls[i]

    train_dl,valid_dl = add_props(lambda i,x: x[i])
    train_ds,valid_ds = add_props(lambda i,x: x[i].dataset)

    _docs=dict(__getitem__="Retrieve `DataLoader` at `i` (`0` is training, `1` is validation)",
              train_dl="Training `DataLoader`",
              valid_dl="Validation `DataLoader`",
              train_ds="Training `Dataset`",
              valid_ds="Validation `Dataset`")

#Cell
class FilteredBase:
    "Base class for lists with subsets"
    _dl_type = TfmdDL
    def __init__(self, *args, dl_type=None, **kwargs):
        self.dl_type = self._dl_type if dl_type is None else dl_type
        self.databunch = delegates(self.dl_type.__init__)(self.databunch)
        super().__init__(*args, **kwargs)

    def _new(self, items, **kwargs): return super()._new(items, splits=self.splits, **kwargs)
    def subset(self): raise NotImplemented
    @property
    def n_subsets(self): return len(self.splits)

    def databunch(self, bs=16, val_bs=None, shuffle_train=True, **kwargs):
        n = self.n_subsets-1
        bss = [bs] + [2*bs]*n if val_bs is None else [bs] + [val_bs]*n
        shuffles = [shuffle_train] + [False]*n
        return DataBunch(*[self.dl_type(self.subset(i), bs=b, shuffle=s, drop_last=s, **kwargs)
                               for i,(b,s) in enumerate(zip(bss, shuffles))])

FilteredBase.train,FilteredBase.valid = add_props(lambda i,x: x.subset(i), 2)

#Cell
class TfmdList(FilteredBase, L):
    "A `Pipeline` of `tfms` applied to a collection of `items`"
    _default='tfms'
    def __init__(self, items, tfms, use_list=None, do_setup=True, as_item=True, split_idx=None, train_setup=True, splits=None, dl_type=None):
        super().__init__(items, use_list=use_list, dl_type=dl_type)
        self.splits = L([slice(None)] if splits is None else splits).map(mask2idxs)
        if isinstance(tfms,TfmdList): tfms = tfms.tfms
        if isinstance(tfms,Pipeline): do_setup=False
        self.tfms = Pipeline(tfms, as_item=as_item, split_idx=split_idx)
        if do_setup: self.setup(train_setup=train_setup)

    def _new(self, items, **kwargs): return super()._new(items, tfms=self.tfms, do_setup=False, **kwargs)
    def subset(self, i): return self._new(self._get(self.splits[i]), split_idx=i)
    def _after_item(self, o): return self.tfms(o)
    def __repr__(self): return f"{self.__class__.__name__}: {self.items}\ntfms - {self.tfms.fs}"
    def __iter__(self): return (self[i] for i in range(len(self)))
    def show(self, o, **kwargs): return self.tfms.show(o, **kwargs)
    def decode(self, x, **kwargs): return self.tfms.decode(x, **kwargs)
    def __call__(self, x, **kwargs): return self.tfms.__call__(x, **kwargs)
    def setup(self, train_setup=True): self.tfms.setup(getattr(self,'train',self) if train_setup else self)

    def __getitem__(self, idx):
        res = super().__getitem__(idx)
        if self._after_item is None: return res
        return self._after_item(res) if is_indexer(idx) else res.map(self._after_item)

#Cell
def decode_at(o, idx):
    "Decoded item at `idx`"
    return o.decode(o[idx])

#Cell
def show_at(o, idx, **kwargs):
    "Show item at `idx`",
    return o.show(o[idx], **kwargs)

#Cell
@docs
@delegates(TfmdList)
class DataSource(FilteredBase):
    "A dataset that creates a tuple from each `tfms`, passed thru `ds_tfms`"
    def __init__(self, items=None, tfms=None, tls=None, n_inp=None, **kwargs):
        self.tls = L(tls if tls else [TfmdList(items, t, **kwargs) for t in L(ifnone(tfms,[None]))])
        self.n_inp = (1 if len(self.tls)==1 else len(self.tls)-1) if n_inp is None else n_inp

    def __getitem__(self, it):
        res = tuple([tl[it] for tl in self.tls])
        return res if is_indexer(it) else list(zip(*res))

    def __getattr__(self,k): return gather_attrs(self, k, 'tls')
    def __len__(self): return len(self.tls[0])
    def __iter__(self): return (self[i] for i in range(len(self)))
    def __repr__(self): return coll_repr(self)
    def decode(self, o): return tuple(tl.decode(o_) for o_,tl in zip(o,self.tls))
    def subset(self, i): return type(self)(tls=L(tl.subset(i) for tl in self.tls))
    def _new(self, items, *args, **kwargs): return super()._new(items, tfms=self.tfms, do_setup=False, **kwargs)
    @property
    def splits(self): return self.tls[0].splits
    @property
    def split_idx(self): return self.tls[0].tfms.split_idx

    def show(self, o, ctx=None, **kwargs):
        for o_,tl in zip(o,self.tls): ctx = tl.show(o_, ctx=ctx, **kwargs)
        return ctx

    _docs=dict(
        decode="Compose `decode` of all `tuple_tfms` then all `tfms` on `i`",
        show="Show item `o` in `ctx`",
        databunch="Get a `DataBunch`",
        subset="New `DataSource` that only includes subset `i`")

#Cell
def test_set(dsrc, test_items):
    "Create a test set from `test_items` using validation transforms of `dsrc`"
    test_tls = [tl._new(test_items, split_idx=1) for tl in dsrc.tls[:dsrc.n_inp]]
    return DataSource(tls=test_tls)

#Cell
def test_dl(dbunch, test_items):
    "Create a test dataloader from `test_items` using validation transforms of `dbunch`"
    test_ds = test_set(dbunch.valid_ds, test_items)
    return dbunch.valid_dl.new(test_ds)