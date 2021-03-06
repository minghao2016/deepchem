"""
Contains basic hyperparameter optimizations.
"""
import numpy as np
import os
import itertools
import tempfile
import shutil
import collections
from functools import reduce
from operator import mul
from deepchem.utils.evaluate import Evaluator
from deepchem.utils.save import log

class HyperparamOpt(object):
  """
  Provides simple hyperparameter search capabilities.
  """

  def __init__(self, model_class, verbosity="high"):
    self.model_class = model_class
    assert verbosity in [None, "low", "high"]
    self.verbosity = verbosity

  # TODO(rbharath): This function is complicated and monolithic. Is there a nice
  # way to refactor this?
  def hyperparam_search(self, params_dict, train_dataset, valid_dataset,
                        output_transformers, metric, use_max=True,
                        logdir=None):
    """Perform hyperparams search according to params_dict.
    
    Each key to hyperparams_dict is a model_param. The values should be a list
    of potential values for that hyperparam. 

    TODO(rbharath): This shouldn't be stored in a temporary directory.
    """ 
    hyperparams = params_dict.keys()
    hyperparam_vals = params_dict.values() 
    for hyperparam_list in params_dict.values():
      assert isinstance(hyperparam_list, collections.Iterable)

    number_combinations = reduce(mul, [len(vals) for vals in hyperparam_vals])

    valid_csv_out = tempfile.NamedTemporaryFile()
    valid_stats_out = tempfile.NamedTemporaryFile()
    if use_max:
      best_validation_score = -np.inf
    else:
      best_validation_score = np.inf
    best_hyperparams = None
    best_model, best_model_dir = None, None
    all_scores = {}
    for ind, hyperparameter_tuple in enumerate(itertools.product(*hyperparam_vals)):
      model_params = {}
      log("Fitting model %d/%d" % (ind+1, number_combinations),
          self.verbosity, "high")
      for hyperparam, hyperparam_val in zip(hyperparams, hyperparameter_tuple):
        model_params[hyperparam] = hyperparam_val
      log("hyperparameters: %s" % str(model_params),
          self.verbosity, "high")

      if logdir is not None:
        model_dir = os.path.join(logdir, str(ind))
        log("model_dir is %s" % model_dir, self.verbosity, "high")
        try: 
          os.makedirs(model_dir)
        except OSError:
          if not os.path.isdir(model_dir):
            log("Error creating model_dir, using tempfile directory", self.verbosity, "high")
            model_dir = tempfile.mkdtemp()
      else:
        model_dir = tempfile.mkdtemp()

      model = self.model_class(model_params, model_dir)
      model.fit(train_dataset, **model_params)
      model.save()
    
      evaluator = Evaluator(model, valid_dataset, output_transformers)
      multitask_scores = evaluator.compute_model_performance(
          [metric], valid_csv_out.name, valid_stats_out.name)
      valid_score = multitask_scores[metric.name]
      all_scores[str(hyperparameter_tuple)] = valid_score
    
      if (use_max and valid_score >= best_validation_score) or (
          not use_max and valid_score <= best_validation_score):
        best_validation_score = valid_score
        best_hyperparams = hyperparameter_tuple
        if best_model_dir is not None:
          shutil.rmtree(best_model_dir)
        best_model_dir = model_dir
        best_model = model
      else:
        shutil.rmtree(model_dir)
  
      log("Model %d/%d, Metric %s, Validation set %s: %f" %
          (ind+1, number_combinations, metric.name, ind, valid_score),
          self.verbosity, "low")
      log("\tbest_validation_score so far: %f" % best_validation_score,
          self.verbosity, "low")
    if best_model is None:
      log("No models trained correctly.", self.verbosity, "low")
      # arbitrarily return last model
      best_model, best_hyperparams = model, hyperparameter_tuple
      return best_model, best_hyperparams, all_scores
    train_csv_out = tempfile.NamedTemporaryFile()
    train_stats_out = tempfile.NamedTemporaryFile()
    train_evaluator = Evaluator(best_model, train_dataset, output_transformers)
    multitask_scores = train_evaluator.compute_model_performance(
        [metric], train_csv_out.name, train_stats_out.name)
    train_score = multitask_scores[metric.name]
    log("Best hyperparameters: %s" % str(best_hyperparams),
        self.verbosity, "low")
    log("train_score: %f" % train_score, self.verbosity, "low")
    log("validation_score: %f" % best_validation_score, self.verbosity, "low")
    return best_model, best_hyperparams, all_scores
