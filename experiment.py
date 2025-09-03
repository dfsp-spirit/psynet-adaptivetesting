import random

import psynet.experiment
from psynet.asset import LocalStorage, OnDemandAsset, S3Storage  # noqa
from psynet.modular_page import (
    AudioPrompt,
    AudioRecordControl,
    ModularPage,
)
from psynet.page import InfoPage, VolumeCalibration
from psynet.timeline import Timeline, CodeBlock, PageMaker, while_loop, join
from psynet.trial.static import StaticNode, StaticTrial, StaticTrialMaker
from psynet.consent import NoConsent


from adaptivetesting.implementations import TestAssembler
from adaptivetesting.models import AdaptiveTest, ItemPool, TestItem
from adaptivetesting.data import CSVContext
from adaptivetesting.math.estimators import BayesModal, CustomPrior
from adaptivetesting.math.item_selection import maximum_information_criterion
from scipy.stats import t
import pandas as pd
from typing import Union





# Here we define the stimulus set in an analogous way to the static_audio demo,
# except we randomise the start_frequency from a continuous range.
nodes = [
    StaticNode(
        definition={
            "frequency_gradient": frequency_gradient,
        },
    )
    for frequency_gradient in [-100, -50, 0, 50, 100]
]


class CustomTrial(StaticTrial):
    _time_trial = 3
    _time_feedback = 2

    time_estimate = _time_trial + _time_feedback
    wait_for_feedback = True

    def finalize_definition(self, definition, experiment, participant):
        definition["start_frequency"] = random.uniform(-100, 100)
        definition["frequencies"] = [
            definition["start_frequency"] + i * definition["frequency_gradient"]
            for i in range(5)
        ]
        self.add_assets(
            {
                "stimulus": OnDemandAsset(
                    function=synth_stimulus,
                    extension=".wav",
                )
            }
        )
        return definition

    def show_trial(self, experiment, participant):
        return ModularPage(
            "imitation",
            AudioPrompt(
                self.assets["stimulus"],
                "Please imitate the spoken word as closely as possible.",
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
            items_data = pd.DataFrame({
                "a": [1.32, 1.07, 0.84, 1.19, 0.95],  # discrimination
                "b": [-0.63, 0.18, -0.84, 0.41, -0.25],  # difficulty
                "c": [0.17, 0.10, 0.19, 0.15, 0.12],  # guessing
                "d": [0.87, 0.93, 1.0, 0.89, 0.94]   # upper asymptote
            })
            item_pool = ItemPool.load_from_dataframe(items_data)

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



    def select_next_item(participant):
        test = participant.var.adaptive_test
        assert isinstance(test, AdaptiveTest)
        previous_trials = CustomTrial.query.filter_by(participant_id=participant.id).all()
        print(f"Previous trials: {len(previous_trials)}")


    def evaluate_response(participant):

        def get_response(participant):
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
            print(f"Stopping criterion fulfilled: standard error {adaptive_test.standard_error:.2f} <= 0.4")
            participant.var.stopping_criterion_not_fulfilled = False

        # Also end test if all items have been shown
        if len(adaptive_test.item_pool.test_items) == 0:
            print(f"Stopping criterion fulfilled: all items have been shown.")
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
        StaticTrialMaker(
            id_="static_audio_2",
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
                CodeBlock(select_next_item),  # loads the adaptive test, and sets the current_item
                PageMaker(lambda participant: CustomTrial.cue({
                    "item": participant.var.current_item,
                }), time_estimate=10.0),
                CodeBlock(evaluate_response),
            ),
            expected_repetitions=35,  # just for progress indication (not a hard limit)
        ),
    )
