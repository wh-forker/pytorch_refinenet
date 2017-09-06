import torch.nn as nn
import torchvision.models as models

from .blocks import (
    RefineNetBlock,
    ResidualConvUnit
)


class RefineNet(nn.Module):

    def __init__(self, input_shape,
                 num_classes=1,
                 features=256,
                 resnet_factory=models.resnet101,
                 pretrained=True,
                 freeze_resnet=True):
        """Multi-path refinenet for image segmentation

        Args:
            input_shape ((int, int)): (channel, size) assumes input has
                equal height and width
            num_classes (int, optional): number of classes
            features (int, optional): number of features in refinenet
            resnet_factory (func, optional): A Resnet model from torchvision.
                Default: models.resnet101
            pretrained (bool, optional): Use pretrained version of resnet
                Default: True
            freeze_resnet (bool, optional): Freeze resnet model
                Default: True

        Raises:
            ValueError: size of input_shape not divisible by 32
        """
        super().__init__()

        input_channel, input_size = input_shape

        if input_size % 32 != 0:
            raise ValueError(f"{input_shape} not divisble by 32")

        resnet = resnet_factory(pretrained=pretrained)

        self.layer1 = nn.Sequential(
            resnet.conv1,
            resnet.bn1,
            resnet.relu,
            resnet.maxpool,
            resnet.layer1
        )

        self.layer2 = resnet.layer2
        self.layer3 = resnet.layer3
        self.layer4 = resnet.layer4

        if freeze_resnet:
            layers = [self.layer1, self.layer2, self.layer3, self.layer4]
            for layer in layers:
                for param in layer.parameters():
                    param.requires_grad = False

        self.layer1_rn = nn.Conv2d(256, features, kernel_size=3, stride=1, padding=1, bias=False)
        self.layer2_rn = nn.Conv2d(512, features, kernel_size=3, stride=1, padding=1, bias=False)
        self.layer3_rn = nn.Conv2d(1024, features, kernel_size=3, stride=1, padding=1, bias=False)
        self.layer4_rn = nn.Conv2d(2048, features, kernel_size=3, stride=1, padding=1, bias=False)

        self.refinenet4 = RefineNetBlock(
            2*features, (2*features, input_size // 32))
        self.refinenet3 = RefineNetBlock(
            features, (2*features, input_size // 32), (features, input_size // 16))
        self.refinenet2 = RefineNetBlock(
            features, (features, input_size // 16), (features, input_size // 8))
        self.refinenet1 = RefineNetBlock(
            features, (features, input_size // 8), (features, input_size // 4))

        self.output_conv = nn.Sequential(
            ResidualConvUnit(features),
            ResidualConvUnit(features),
            nn.Conv2d(features, num_classes, kernel_size=1, stride=1, padding=0, bias=True)
        )

    def forward(self, x):

        layer_1 = self.layer1(x)
        layer_2 = self.layer2(layer_1)
        layer_3 = self.layer3(layer_2)
        layer_4 = self.layer4(layer_3)

        layer_1_rn = self.layer1_rn(layer_1)
        layer_2_rn = self.layer2_rn(layer_2)
        layer_3_rn = self.layer3_rn(layer_3)
        layer_4_rn = self.layer4_rn(layer_4)

        path_4 = self.refinenet4(layer_4_rn)
        path_3 = self.refinenet3(path_4, layer_3_rn)
        path_2 = self.refinenet2(path_3, layer_2_rn)
        path_1 = self.refinenet1(path_2, layer_1_rn)
        out = self.output_conv(path_1)
        return out
