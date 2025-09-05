import random

import psynet.experiment
from psynet.asset import LocalStorage, OnDemandAsset, S3Storage, asset  # noqa
from psynet.modular_page import (
    AudioPrompt,
    Prompt,
    AudioRecordControl,
    ModularPage,
    RadioButtonControl
)
from psynet.page import InfoPage
from psynet.timeline import Timeline, CodeBlock, PageMaker, while_loop, join
from psynet.trial.static import StaticNode, StaticTrial, StaticTrialMaker
from psynet.trial.main import Trial
from psynet.consent import NoConsent
from psynet.participant import Participant


from adaptivetesting.implementations import TestAssembler
from adaptivetesting.models import AdaptiveTest, ItemPool, TestItem
from adaptivetesting.math.estimators import BayesModal, CustomPrior
from adaptivetesting.math.item_selection import maximum_information_criterion
from scipy.stats import t
import pandas as pd
from typing import Union, Dict, NoReturn, List



g_items_data = pd.DataFrame({   # see catR R package documentation for details on parameters
    "a": [1.32, 1.07, 0.84, 1.19, 0.95],  # discrimination
    "b": [-0.63, 0.18, -0.84, 0.41, -0.25],  # difficulty
    "c": [0.17, 0.10, 0.19, 0.15, 0.12],  # guessing
    "d": [0.87, 0.93, 1.0, 0.89, 0.94],  # upper asymptote
    "stimulusfile": ["static/bier.wav", "static/baum.wav", "static/haus.wav",
                     "static/auto.wav", "static/boot.wav"]
})


class CustomTrial(Trial):

    time_estimate = 10.0  # seconds

    def show_trial(self, experiment : psynet.experiment.Experiment, participant : Participant) -> ModularPage:
        print(f"CustomTrial.show_trial() for participant {participant.id}: self.definition: {self.definition}")

        item: TestItem = self.definition['item']
        assert isinstance(item, TestItem), f"Expected item to be TestItem, got {type(item)}"
        print(f"CustomTrial.show_trial(): Selected item as dict: {item.as_dict()}")
        item_difficulty: float = item.b
        stimuli_list: pd.Series = g_items_data.loc[g_items_data["b"] == item_difficulty, "stimulusfile"] # TODO: avoid accessing global variable. Requires my patch for adaptive_test.itempool, which currently does not store IDs.
        selected_stimulus_file: str = stimuli_list.values[0]

        assert isinstance(selected_stimulus_file, str), f"Expected stimulus to be str, got {type(selected_stimulus_file)}"

        return ModularPage(
            "sound_comparison",
            Prompt(
                # In the real experiment, we play an audio file that contains two sounds: sound A, then a pause, then sound B.
                # In this demo experiment, we don't play any sound. We just print the filename of the sound we would play as a text message.
                text=f"Please listen to the 2 sounds from file '{selected_stimulus_file}' as closely as possible. Were they identical? (NOTE: In this demo, no sounds are played, just selected a random answer.)",
            ),
            RadioButtonControl(
                choices=["yes", "no"],
                labels=["Yes, they were identical.",
                        "No, they were not identical."],
            ),
            time_estimate=10,
        )


class Exp(psynet.experiment.Experiment):

    ## PsyNet experiment configuration
    label = "Adaptive Testing"
    psynet.experiment.Experiment.max_exp_dir_size_in_mb = 2000   # Prevent error if exceeding the default 256 MB limit.
    consent_page = NoConsent()
    asset_storage = LocalStorage()

    @staticmethod
    def create_adaptivetest_instance(items_difficulty_csvfile: Union[str, None] = None) -> AdaptiveTest:
        """
        Helper function to create an AdaptiveTest instance.
        """
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
                "optimization_interval": (-10, 10)
            },
            item_selector=maximum_information_criterion,
            simulation=False,
            debug=False
        )
        return adaptive_test

    @staticmethod
    def set_participant_current_item(participant: Participant) -> NoReturn:
        """
        Sets the current_item variable of the participant to the next item selected by the adaptive test.
        """
        adaptive_test: AdaptiveTest = participant.var.adaptive_test
        assert isinstance(adaptive_test, AdaptiveTest), f"Expected adaptive_test to be AdaptiveTest, got {type(adaptive_test)}"
        # previous_trials = CustomTrial.query.filter_by(participant_id=participant.id).all()
        # print(f"Previous trials: {len(previous_trials)}")
        next_item: TestItem = adaptive_test.get_next_item()
        print(f"select_next_item_id for participant {participant.id}: Selected next item: {next_item.as_dict()}")
        participant.var.set("current_item", next_item)


    @staticmethod
    def evaluate_response(participant: Participant) -> NoReturn:

        print(f"###### evaluate_response: starting to evaluate response for participant {participant.id}... #####")
        print(f"evaluate_response: participant answer: {participant.answer}")

        def get_response(participant: Participant) -> int:
            return participant.answer

        adaptive_test: AdaptiveTest = participant.var.adaptive_test
        assert isinstance(adaptive_test, AdaptiveTest), f"Expected adaptive_test to be AdaptiveTest, got {type(adaptive_test)}"
        adaptive_test.get_response = get_response
        print(f"evaluate_reponse: running adaptive_test.run_test_once()...")
        adaptive_test.run_test_once()
        participant.var.adaptive_test = adaptive_test # update participant variable

        #all_item_difficulties: List[float] = adaptive_test.get_item_difficulties()
        #print(f"evaluate_reponse: All item difficulties in test pool: {all_item_difficulties}")
        #answered_items_difficulties: List[float] = adaptive_test.get_answered_items_difficulties()
        #print(f"evaluate_reponse: Answered item difficulties: {answered_items_difficulties}")

        # Check whether stopping criterion is fulfilled
        if adaptive_test.standard_error <= 0.4:
            print(
                f"evaluate_reponse: Stopping criterion A fulfilled: standard error {adaptive_test.standard_error:.2f} <= 0.4")
            participant.var.stopping_criterion_not_fulfilled = False

        # Also end test if all items have been shown
        if len(adaptive_test.item_pool.test_items) == 0:
            print(
                f"evaluate_reponse: Stopping criterion B fulfilled: all items have been shown.")
            participant.var.stopping_criterion_not_fulfilled = False

        #print(f"evaluate_reponse: current ability estimate: {adaptive_test.ability:.2f}, standard error: {adaptive_test.standard_error:.2f}")
        #print(f"###### evaluate_response: finished evaluating response for participant {participant.id}. #####")


    timeline = Timeline(
        InfoPage(
            """
            In this experiment you will hear two melodies per trial, with a short pause in between. Your task is to listen carefully and decide whether they are identical or not.
            """,
            time_estimate=5,
        ),
        lambda participant: participant.var.set(
            "adaptive_test", Exp.create_adaptivetest_instance()),
        lambda participant: participant.var.set(
            "stopping_criterion_not_fulfilled", True),
        lambda participant: participant.var.set("current_item", None),
        CodeBlock(set_participant_current_item),
        while_loop(
            label="Adaptive test loop",
            condition=lambda participant: participant.var.stopping_criterion_not_fulfilled,
            logic=join(
                PageMaker(lambda participant: CustomTrial.cue(definition={
                    "item": participant.var.current_item,
                }, assets=None), time_estimate=10.0),
                CodeBlock(evaluate_response),
                CodeBlock(set_participant_current_item),
            ),
            expected_repetitions=g_items_data.shape[0],
        ),
    )
