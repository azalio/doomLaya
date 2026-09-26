"""Optional categorical decoding of model probabilities; no game-state rules."""
import math
import random


class ChoiceDecoder:
    def __init__(self,temperature=0.,seed=0,questions=None):
        if not math.isfinite(temperature) or temperature<0:
            raise ValueError('temperature must be finite and nonnegative')
        self.temperature=temperature
        self.seed=seed
        self.questions=None if questions is None else frozenset(questions)
        self.random=random.Random(seed)
        self.draws=0

    def metadata(self):
        return dict(method='categorical' if self.temperature else 'argmax',
                    temperature=self.temperature,seed=self.seed,
                    questions=None if self.questions is None else sorted(self.questions))

    def apply(self,result):
        if not self.temperature:return result
        for name,answer in result['answers'].items():
            if answer['type']!='choice' or (self.questions is not None and name not in self.questions):continue
            probabilities=answer['probabilities'];keys=list(probabilities)
            logs=[math.log(probabilities[k])/self.temperature if probabilities[k]>0 else -math.inf for k in keys]
            maximum=max(logs)
            if not math.isfinite(maximum):raise ValueError('empty probability support')
            weights=[math.exp(value-maximum) for value in logs];total=sum(weights)
            answer['choice']=self.random.choices(keys,weights=weights,k=1)[0]
            self.draws+=1
            answer['decoding']=dict(self.metadata(),draw=self.draws,
                                    probabilities={k:w/total for k,w in zip(keys,weights)})
        return result
