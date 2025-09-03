import random

import psynet.experiment
from psynet.asset import LocalStorage, OnDemandAsset, S3Storage, asset  # noqa
from psynet.modular_page import (
    AudioPrompt,
    AudioRecordControl,
    ModularPage,
)
from psynet.page import InfoPage, VolumeCalibration
from psynet.timeline import Timeline, CodeBlock, PageMaker, while_loop, join
from psynet.trial.static import StaticNode, StaticTrial, StaticTrialMaker
from psynet.consent import NoConsent
from psynet.participant import Participant


from adaptivetesting.implementations import TestAssembler
from adaptivetesting.models import AdaptiveTest, ItemPool, TestItem
from adaptivetesting.data import CSVContext
from adaptivetesting.math.estimators import BayesModal, CustomPrior
from adaptivetesting.math.item_selection import maximum_information_criterion
from scipy.stats import t
import pandas as pd
from typing import Union, Dict, NoReturn, List


#In catR (the R package for computerized adaptive testing), the a, b, c, d parameters are the item parameters from Item Response Theory (IRT) models. Their meaning depends on which IRT model you are using:
#
#a → discrimination parameter
#  How well the item differentiates between examinees with different ability levels (slope of the ICC).
#  Higher a means the item is more informative around its difficulty point.
#
#b → difficulty parameter
#  The ability level (θ) at which the probability of a correct response is 50% (in the 2PL and 3PL models).
#  Shifts the item response curve left or right.
#
#c → guessing parameter
#  Lower asymptote of the item characteristic curve.
#  Represents the probability of a correct answer by guessing (often relevant in multiple-choice tests).
#
#d → upper asymptote
#  Upper bound of the item characteristic curve (instead of 1.0).
#  Useful in the 4PL model if items have less-than-perfect maximum performance (slipping, careless errors, etc.).


g_items_data = pd.DataFrame({
                "a": [1.32, 1.07, 0.84, 1.19, 0.95],  # discrimination
                "b": [-0.63, 0.18, -0.84, 0.41, -0.25],  # difficulty
                "c": [0.17, 0.10, 0.19, 0.15, 0.12],  # guessing
                "d": [0.87, 0.93, 1.0, 0.89, 0.94],  # upper asymptote
                "stimulusfile": ["static/bier.wav", "static/baum.wav", "static/haus.wav", "static/auto.wav", "static/boot.wav"]
            })


# Here we define the stimulus set in an analogous way to the static_audio demo,
# except we randomise the start_frequency from a continuous range.
nodes = [
    StaticNode(
        definition={
            "frequency_gradient": frequency_gradient,
            "wait_seconds_between_stimuli": 5.0,
        },
    )
    for frequency_gradient in [-100, -50, 0, 50, 100]
]


class CustomTrial(StaticTrial):
    _time_trial = 3
    _time_feedback = 2

    time_estimate = _time_trial + _time_feedback
    wait_for_feedback = True

    def finalize_definition(self, definition : Dict, experiment : psynet.experiment.Experiment, participant : Participant) -> Dict:
        definition["start_frequency"] = random.uniform(-100, 100)
        definition["frequencies"] = [
            definition["start_frequency"] + i * definition["frequency_gradient"]
            for i in range(5)
        ]
        adaptive_test : AdaptiveTest = participant.var.adaptive_test
        assert isinstance(adaptive_test, AdaptiveTest)
        item : TestItem = adaptive_test.get_next_item()
        print(f"Selected item ID: {item.id}, a: {item.a}, b: {item.b}, c: {item.c}, d: {item.d}")
        print(f"Selected item as dict: {item.as_dict()}")
        stimulus_id : Union[int, None] = item.id
        if not isinstance(stimulus_id, int):
            print(f"Warning: item ID is not an int, but {type(stimulus_id)}. Setting stimulus_id to -1.")
            stimulus_id = -1

        definition["stimulus_id"] = stimulus_id

        item_difficulty: float = item.b
        stimuli_list: pd.Series = g_items_data.loc[g_items_data["b"] == item_difficulty, "stimulusfile"]
        stimulus: str = stimuli_list.values[0]
        print(f"Selected stimulus file: '{stimulus}'.")

        definition["stimulus"] = stimulus

        #print(f"Creating asset from stimulus file '{stimulus}'...")
        #self.add_assets(
        #    {
        #        "stimulus": asset(stimulus)
        #    }
        #)
        return definition

    def show_trial(self, experiment, participant):
        return ModularPage(
            "imitation",
            AudioPrompt(
                #self.assets["stimulus"],
                self.definition["stimulus"],
                text="Please imitate the spoken word as closely as possible.",
            ),
            AudioRecordControl(duration=3.0, bot_response_media="example-bier.wav"),
            time_estimate=self._time_trial,
        )



class Exp(psynet.experiment.Experiment):

    # PsyNet experiment configuration
    label = "Adaptive Testing"
    psynet.experiment.Experiment.max_exp_dir_size_in_mb = 2000   # Prevent error if exceeding the default 256 MB limit.
    consent_page = NoConsent()
    asset_storage = LocalStorage()


    # Adaptive testing configuration
    # Create item pool from DataFrame


    # Create adaptive test
    def create_adaptivetest_instance(items_difficulty_csvfile : Union[str, None] = None) -> AdaptiveTest:

        if items_difficulty_csvfile:
            # Load item parameters from CSV file
            data_frame = pd.read_csv(items_difficulty_csvfile)
            item_pool = ItemPool.load_from_dataframe(data_frame)

        else:
            print(f"No CSV file provided, using default item parameters.")
            item_pool = ItemPool.load_from_dataframe(g_items_data)

        adaptive_test: AdaptiveTest = TestAssembler(
            item_pool=item_pool,
            simulation_id="example",
            participant_id="dummy",
            ability_estimator=BayesModal,
            estimator_args={
                "prior": CustomPrior(t, 100),
                "optimization_interval":(-10, 10)
            },
            item_selector=maximum_information_criterion,
            simulation=False,
            debug=False
        )
        return adaptive_test



    def select_next_item_id(participant : Participant) -> NoReturn:
        """
        Sets the current_item variable of the participant to the next item selected by the adaptive test.
        """
        adaptive_test : AdaptiveTest = participant.var.adaptive_test
        assert isinstance(adaptive_test, AdaptiveTest)
        #previous_trials = CustomTrial.query.filter_by(participant_id=participant.id).all()
        #print(f"Previous trials: {len(previous_trials)}")
        next_item: TestItem = adaptive_test.select_next_item()
        participant.var.set("current_item", next_item)


    def evaluate_response(participant : Participant) -> NoReturn:

        def get_response(participant : Participant) -> int:
            return participant.answer

        adaptive_test = participant.var.adaptive_test
        adaptive_test.get_response = get_response
        adaptive_test.run_test_once()
        # Careful: watch out for PsyNet not updating the participant.var.adaptive_test,
        # because it's an inplace update.
        # This should hopefully work though:
        participant.var.adaptive_test = adaptive_test

        # Check whether stopping criterion is fulfilled
        if adaptive_test.standard_error <= 0.4:
            print(f"Stopping criterion A fulfilled: standard error {adaptive_test.standard_error:.2f} <= 0.4")
            participant.var.stopping_criterion_not_fulfilled = False

        # Also end test if all items have been shown
        if len(adaptive_test.item_pool.test_items) == 0:
            print(f"Stopping criterion B fulfilled: all items have been shown.")
            participant.var.stopping_criterion_not_fulfilled = False



    timeline = Timeline(
        InfoPage(
            """
            In this experiment you will hear some words. Your task will be to repeat
            them back as accurately as possible.
            """,
            time_estimate=5,
        ),
        lambda participant: participant.var.set("adaptive_test", Exp.create_adaptivetest_instance()),
        lambda participant: participant.var.set("stopping_criterion_not_fulfilled", True),
        lambda participant: participant.var.set("current_item", None),
        StaticTrialMaker(
            id_="adaptivetesting",
            trial_class=CustomTrial,
            nodes=nodes,
            expected_trials_per_participant=len(nodes),
            target_n_participants=3,
            recruit_mode="n_participants",
        ),
        while_loop(
           label="Adaptive test loop",
            condition=lambda participant: participant.var.stopping_criterion_not_fulfilled,
            logic=join(
                CodeBlock(select_next_item_id),  # loads the adaptive test, and sets the current_item variable of participant
                PageMaker(lambda participant: CustomTrial.cue({
                    "item": participant.var.current_item,
                }), time_estimate=10.0),
                CodeBlock(evaluate_response),
            ),
            expected_repetitions=35,  # just for progress indication (not a hard limit)
        ),
    )
