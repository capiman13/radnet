# https://blog.metaflow.fr/tensorflow-how-to-freeze-a-model-and-serve-it-with-a-python-api-d4f3596b3adc#.dykqbzqek
# https://medium.com/@hamedmp/exporting-trained-tensorflow-models-to-c-the-right-way-cf24b609d183#.2yffldwf7
# https://github.com/tensorflow/tensorflow/issues/616


from tensorflow.core.framework import graph_pb2
from tensorflow.python.client import session
from tensorflow.python.framework import importer
from tensorflow.python.framework import ops
import numpy as np
import scipy.interpolate

class RadNet:
    """ Class for loading and fetching the model for getting predictions.

    """

    # TODO: the names of the items of this dict should be changed to match the names of the
    # variables used in the program data calls this class.

    HUMIDITY = "humidity"
    AIR_TEMPERATURE = "air_temperature"
    SURFACE_TEMPERATURE = "surface_temperature"
    CO2 = "CO2"

    STATISTIC_PARAMS = {
        AIR_TEMPERATURE: {
            "min": 100.0000000000,
            "max": 355.5721906214,
            "mean": 230.1788102309,
            "std": 46.5063403685
        },
        HUMIDITY: {
            "min": -2720.3344538111,
            "max": 1848.3667831706,
            "mean": 4.2050377031,
            "std": 13.4852605066
        },
        SURFACE_TEMPERATURE: {
            "min": 100.0000000000,
            "max": 333.1499946801,
            "mean": 268.1406929063,
            "std": 37.5368706325
        },
        CO2: {
            "min": 0.0000000000,
            "max": 0.0099999904,
            "mean": 0.0017284657,
            "std": 0.0023850203
        }
    }

    def __init__(self, frozen_graph_path):
        """ Initializes the needed variables for making prediction

        Loads the graph from a frozen graph in protobbuf format file generated after training the model.
        Then starts a Tensorflow session with that graph and gets the needed variables for
        fetching the model in further calls. The session is then initialized once.

        :param frozen_graph_path: path to the protobuf (.pb) file containing the graph and the value
        of the variables.
        """
        self.input_size = 96

        with ops.Graph().as_default():
            output_graph_def = graph_pb2.GraphDef()

            with open(frozen_graph_path, "rb") as f:
                output_graph_def.ParseFromString(f.read())
                _ = importer.import_graph_def(output_graph_def, name="")



            # We are initializing the session with the default graph which already has the
            # frozen graph loaded.
            self.sess = session.Session()

            # Important loop for printing the nodes of the graph and debugging
            #for op in self.sess.graph.get_operations():
            #    print(op.name)

            # The input and output nodes are gotten into a variable
            self.input_node = self.sess.graph.get_tensor_by_name("create_model/radnet_1/input_node:0")
            self.output_node = self.sess.graph.get_tensor_by_name("create_model/radnet_1/out/output_node:0")
            # Getting the train_flag_node is also required as it is like that and we need to indicate the graph
            # we are just fetching a parameter.
            self.train_flag_node = self.sess.graph.get_tensor_by_name("create_model/train_bool_node:0")

    def predict(self, sample, output_size=96):
        """ Method for fetching the model

        :param sample: array[196] with the correct input of the model
        :return prediction: array[96] with the radiation level for each of the 26 layers
        """

        # Line to be uncommented with the climt integration
        sample = self.__pre_process(sample)
        prediction = self.sess.run(
                self.output_node,
                feed_dict={
                     self.input_node: [sample],
                     self.train_flag_node: False
                })

        # Interpolates de output to the wished value size
        prediction = self.__interpolate(prediction.squeeze(), output_size)

        return prediction

    def __interpolate(self, input, output_size=96):
        """ spline interpolation for reducing/augmenting the number of levels.

        :param input: array with a parameter to be interpolated
        :param output_size: number of layers to be interpolated, 96 by default
        :return: array[arrays] with variables for 96 hundred layers
        """
        size = len(input)
        if size == output_size:
            return input


        print(input)

        # 100 is just a number that shouldn't matter if is changed
        x = np.linspace(0, 100, size)
        x_ext = np.linspace(0, 100, output_size)

        func = scipy.interpolate.splrep(x, input, s=0)
        input_ext = scipy.interpolate.splev(x_ext, func, der=0)
        data = input_ext
        print(data)

        return data

    def __pre_process(self, inputs):
        """ Method that prepares the data for fetching the model.

        :param inputs:
        :return:
        """
        data = {}
        for key, value in inputs.items():
            if isinstance(value, list):
                value = self.__normalize(
                    value,
                    self.STATISTIC_PARAMS[key]['mean'],
                    self.STATISTIC_PARAMS[key]['std'])

                # Interpolate the data into the x parameters per layer.
                print(key)
                value = self.__interpolate(value.squeeze())

            data[key] = value

        # Transform the matrix into the expected input for the model
        input = []
        input.append(data[self.CO2])
        input.append(data[self.SURFACE_TEMPERATURE])
        for i in range(0, self.input_size):
            input.append(data[self.AIR_TEMPERATURE][i])
            input.append(data[self.HUMIDITY][i])

        # fill last 2 values with 0
        # this numbers can be calculated based in the input_size, but I didn't want to do
        # so for simplicity of the code
        for _ in range(0, 196 - 194):
            input.append(0.0)

        return input

    @staticmethod
    def __normalize(x, mean, std):
        if isinstance(x, list):
            x = np.array(x)
        if std == 0:
            return x
        # return  (x - min) / (max - min) # min max normalization
        return (x - mean) / std  # standardization - zero-mean normalization